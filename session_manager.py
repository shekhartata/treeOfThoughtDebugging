"""
MongoDB Session Manager for Tree-of-Thought Debugging Sessions.
Handles persistence of sessions and hypotheses/nodes using normalized collections.
Uses $graphLookup for parent-child tree traversal.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import ReplaceOne
from bson import ObjectId
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages MongoDB persistence for debugging sessions."""
    
    def __init__(self, connection_string: Optional[str] = None, database_name: Optional[str] = None):
        """
        Initialize MongoDB connection.
        
        Args:
            connection_string: MongoDB connection string. If None, reads from MONGODB_URI env var.
            database_name: Database name. If None, extracts from connection string or uses default.
        """
        self.connection_string = connection_string or os.getenv('MONGODB_URI')
        if not self.connection_string:
            raise ValueError(
                "MongoDB connection string required. "
                "Set MONGODB_URI environment variable or pass connection_string parameter."
            )
        
        # Extract database name from connection string if not provided
        if not database_name:
            # Try to extract from connection string (e.g., mongodb://host/dbname or mongodb+srv://host/dbname)
            import re
            # Pattern to match database name in connection string
            match = re.search(r'/([^/?]+)(\?|$)', self.connection_string)
            if match:
                database_name = match.group(1)
            else:
                # Default database name if not in connection string
                database_name = os.getenv('MONGODB_DATABASE_NAME', 'tot_debugging')
        
        self.client = MongoClient(self.connection_string)
        self.db: Database = self.client.get_database(database_name)
        self.sessions: Collection = self.db.sessions
        self.hypotheses: Collection = self.db.hypotheses
        
        # Create indexes
        self._create_indexes()
    
    def _create_indexes(self):
        """Create necessary indexes for efficient queries."""
        try:
            # Sessions collection indexes
            self.sessions.create_index("session_status")
            self.sessions.create_index("updated_at")
            self.sessions.create_index([("session_status", 1), ("updated_at", -1)])
            
            # Hypotheses collection indexes
            self.hypotheses.create_index([("session_id", 1), ("node_id", 1)], unique=True)
            self.hypotheses.create_index([("session_id", 1), ("parent_node_id", 1)])
            self.hypotheses.create_index([("session_id", 1), ("step_number", 1)])
            self.hypotheses.create_index([("session_id", 1), ("hypothesis_id", 1)])
            self.hypotheses.create_index([("session_id", 1), ("hypothesis.status", 1)])
            
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.warning(f"Error creating indexes (may already exist): {e}")
    
    def save_session(self, session_id: str, session_data: Dict, nodes_data: List[Dict]) -> bool:
        """
        Save session and all nodes to MongoDB.
        
        Args:
            session_id: Unique session identifier
            session_data: Session metadata dictionary
            nodes_data: List of node dictionaries to save
        
        Returns:
            True if successful
        """
        try:
            # Prepare session document
            session_doc = {
                "_id": session_id,
                **session_data,
                "updated_at": datetime.utcnow(),
                "last_saved_at": datetime.utcnow()
            }
            
            # Upsert session
            self.sessions.replace_one(
                {"_id": session_id},
                session_doc,
                upsert=True
            )
            
            # Bulk upsert nodes
            if nodes_data:
                bulk_ops = []
                for node in nodes_data:
                    node_doc = {
                        "session_id": session_id,
                        **node
                    }
                    # Use ReplaceOne operation object (not dictionary)
                    bulk_ops.append(
                        ReplaceOne(
                            {
                                "session_id": session_id,
                                "node_id": node["node_id"]
                            },
                            node_doc,
                            upsert=True
                        )
                    )
                
                if bulk_ops:
                    self.hypotheses.bulk_write(bulk_ops, ordered=False)
            
            logger.info(f"Session {session_id} saved successfully ({len(nodes_data)} nodes)")
            return True
            
        except Exception as e:
            logger.error(f"Error saving session {session_id}: {e}", exc_info=True)
            raise
    
    def load_session(self, session_id: str) -> Optional[Dict]:
        """
        Load session metadata from MongoDB.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session document or None if not found
        """
        try:
            session = self.sessions.find_one({"_id": session_id})
            if session:
                # Convert ObjectId to string if present
                if "_id" in session and isinstance(session["_id"], ObjectId):
                    session["_id"] = str(session["_id"])
            return session
        except Exception as e:
            logger.error(f"Error loading session {session_id}: {e}", exc_info=True)
            return None
    
    def load_nodes(self, session_id: str) -> List[Dict]:
        """
        Load all nodes for a session from MongoDB.
        
        Args:
            session_id: Session identifier
        
        Returns:
            List of node documents, sorted by step_number
        """
        try:
            nodes = list(self.hypotheses.find(
                {"session_id": session_id}
            ).sort("step_number", 1))
            
            logger.info(f"Found {len(nodes)} nodes in MongoDB for session {session_id}")
            
            # Convert ObjectIds to strings
            for node in nodes:
                if "_id" in node and isinstance(node["_id"], ObjectId):
                    node["_id"] = str(node["_id"])
            
            # Log first node structure for debugging
            if nodes:
                logger.debug(f"First node keys: {list(nodes[0].keys())}")
                logger.debug(f"First node node_id: {nodes[0].get('node_id')}")
            
            return nodes
        except Exception as e:
            logger.error(f"Error loading nodes for session {session_id}: {e}", exc_info=True)
            return []
    
    def get_tree_with_graphlookup(self, session_id: str, root_node_id: str) -> List[Dict]:
        """
        Get entire tree structure using $graphLookup for parent-child relationships.
        
        Args:
            session_id: Session identifier
            root_node_id: Root node ID to start traversal from
        
        Returns:
            List of nodes with full tree structure populated
        """
        try:
            pipeline = [
                {
                    "$match": {
                        "session_id": session_id,
                        "node_id": root_node_id
                    }
                },
                {
                    "$graphLookup": {
                        "from": "hypotheses",
                        "startWith": "$node_id",
                        "connectFromField": "node_id",
                        "connectToField": "parent_node_id",
                        "as": "descendants",
                        "restrictSearchWithMatch": {
                            "session_id": session_id
                        }
                    }
                },
                {
                    "$unionWith": {
                        "coll": "hypotheses",
                        "pipeline": [
                            {
                                "$match": {
                                    "session_id": session_id,
                                    "parent_node_id": root_node_id
                                }
                            },
                            {
                                "$graphLookup": {
                                    "from": "hypotheses",
                                    "startWith": "$node_id",
                                    "connectFromField": "node_id",
                                    "connectToField": "parent_node_id",
                                    "as": "descendants",
                                    "restrictSearchWithMatch": {
                                        "session_id": session_id
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
            
            results = list(self.hypotheses.aggregate(pipeline))
            
            # Convert ObjectIds to strings
            for result in results:
                if "_id" in result and isinstance(result["_id"], ObjectId):
                    result["_id"] = str(result["_id"])
                if "descendants" in result:
                    for desc in result["descendants"]:
                        if "_id" in desc and isinstance(desc["_id"], ObjectId):
                            desc["_id"] = str(desc["_id"])
            
            return results
        except Exception as e:
            logger.error(f"Error getting tree with graphLookup for session {session_id}: {e}", exc_info=True)
            return []
    
    def get_branch_path(self, session_id: str, node_id: str) -> List[Dict]:
        """
        Get path from root to a specific node using $graphLookup.
        
        Args:
            session_id: Session identifier
            node_id: Target node ID
        
        Returns:
            List of nodes from root to target, ordered by step_number
        """
        try:
            pipeline = [
                {
                    "$match": {
                        "session_id": session_id,
                        "node_id": node_id
                    }
                },
                {
                    "$graphLookup": {
                        "from": "hypotheses",
                        "startWith": "$parent_node_id",
                        "connectFromField": "parent_node_id",
                        "connectToField": "node_id",
                        "as": "ancestors",
                        "restrictSearchWithMatch": {
                            "session_id": session_id
                        }
                    }
                }
            ]
            
            result = list(self.hypotheses.aggregate(pipeline))
            if not result:
                return []
            
            node = result[0]
            ancestors = node.get("ancestors", [])
            
            # Build path: ancestors (root to parent) + current node
            path = sorted(ancestors, key=lambda x: x.get("step_number", 0))
            path.append(node)
            
            # Convert ObjectIds to strings
            for p in path:
                if "_id" in p and isinstance(p["_id"], ObjectId):
                    p["_id"] = str(p["_id"])
            
            return path
        except Exception as e:
            logger.error(f"Error getting branch path for node {node_id}: {e}", exc_info=True)
            return []
    
    def list_unfinished_sessions(self) -> List[Dict]:
        """
        List all active (unfinished) sessions.
        
        Returns:
            List of session documents with metadata
        """
        try:
            sessions = list(self.sessions.find(
                {"session_status": "active"}
            ).sort("updated_at", -1))
            
            # Convert ObjectIds to strings and format for API
            result = []
            for session in sessions:
                if "_id" in session and isinstance(session["_id"], ObjectId):
                    session["_id"] = str(session["_id"])
                
                result.append({
                    "session_id": session["_id"],
                    "problem_summary": session.get("problem_summary", ""),
                    "created_at": session.get("created_at"),
                    "updated_at": session.get("updated_at"),
                    "last_saved_at": session.get("last_saved_at"),
                    "step_counter": session.get("step_counter", 0),
                    "total_nodes": session.get("metadata", {}).get("total_nodes", 0),
                    "total_hypotheses": session.get("metadata", {}).get("total_hypotheses", 0)
                })
            
            return result
        except Exception as e:
            logger.error(f"Error listing unfinished sessions: {e}", exc_info=True)
            return []
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all its nodes.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if successful
        """
        try:
            # Delete nodes first
            self.hypotheses.delete_many({"session_id": session_id})
            
            # Delete session
            result = self.sessions.delete_one({"_id": session_id})
            
            logger.info(f"Session {session_id} deleted (nodes and session)")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
            return False
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
