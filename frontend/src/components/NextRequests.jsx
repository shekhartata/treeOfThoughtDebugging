import React from 'react';
import '../styles/NextRequests.css';

function NextRequests({ requests }) {
  if (!requests || requests.length === 0) {
    return null;
  }

  return (
    <div className="next-requests">
      <strong>📋 Next Data Requests:</strong>
      <ul>
        {requests.map((request, idx) => (
          <li key={idx}>{request}</li>
        ))}
      </ul>
    </div>
  );
}

export default NextRequests;

