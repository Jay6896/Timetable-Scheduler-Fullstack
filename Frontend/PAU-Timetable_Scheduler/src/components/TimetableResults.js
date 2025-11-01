import React, { useState, useEffect } from 'react';
import './TimetableResults.css';
import { getDashUrl, openDashUI } from '../services/api';

const TimetableResults = ({ uploadId }) => {
  const dashAppUrl = getDashUrl(uploadId);

  return (
    <section className="results-section">
      <div className="results-header">
        <div className="results-header-left">
          <div className="results-icon">✓</div>
          <h3 className="results-title">Interactive Timetable</h3>
        </div>
        <div className="results-header-right">
          <button className="open-dash-btn" onClick={() => openDashUI(uploadId)}>Open in new tab</button>
        </div>
      </div>

      <div className="iframe-container">
        <iframe
          src={dashAppUrl}
          title="Interactive Timetable Editor"
          className="timetable-iframe"
        >
          <p>Your browser does not support iframes. Please use a modern browser to view the interactive timetable.</p>
        </iframe>
      </div>
    </section>
  );
};

export default TimetableResults;