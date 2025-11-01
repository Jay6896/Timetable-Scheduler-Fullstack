import React, { useEffect, useRef } from 'react';
import './InstructionsModal.css';

const InstructionsModal = ({ isOpen, onClose }) => {
  const modalRef = useRef(null);
  const firstFocusableRef = useRef(null);

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.classList.add('modal-open');
      
      // Focus management
      if (firstFocusableRef.current) {
        firstFocusableRef.current.focus();
      }
    } else {
      document.body.classList.remove('modal-open');
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.classList.remove('modal-open');
    };
  }, [isOpen, onClose]);

  const handleBackdropClick = (event) => {
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  // Focus trap
  const handleKeyDown = (event) => {
    if (event.key === 'Tab') {
      const focusableElements = modalRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      const firstElement = focusableElements?.[0];
      const lastElement = focusableElements?.[focusableElements.length - 1];

      if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement?.focus();
      }

      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement?.focus();
      }
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div 
      className="modal" 
      onClick={handleBackdropClick}
      onKeyDown={handleKeyDown}
    >
      <div 
        className="modal-content" 
        ref={modalRef}
        role="dialog" 
        aria-labelledby="modal-title" 
        aria-modal="true"
      >
        <div className="modal-header">
          <h3 id="modal-title" className="modal-title">
            How to Use the Timetable Generator
          </h3>
          <button 
            className="close-btn" 
            onClick={onClose}
            aria-label="Close modal"
            type="button"
            ref={firstFocusableRef}
          >
            &times;
          </button>
        </div>
        
        <div className="modal-body">
          <div className="instructions-grid">
            {/* Left Column - Step by Step Instructions */}
            <div className="instructions-steps">
              <div className="instruction-step">
                <h4>Upload Excel File</h4>
                <p>
                  Select and upload your Excel file containing course data. 
                  The file should include subjects, lecturers, rooms, and time preferences. 
                  Supported formats are .xlsx and .xls with a maximum size of 10MB.
                </p>
              </div>
              
              <div className="instruction-step">
                <h4>Generate Timetable</h4>
                <p>
                  Click "Generate Timetable" to process your data. The system will 
                  validate your information and create optimized, conflict-free schedules 
                  for all departments and year levels.
                </p>
              </div>
              
              <div className="instruction-step">
                <h4>Review & Navigate</h4>
                <p>
                  Browse through generated timetables using the carousel controls. 
                  You can swipe on touch devices, use arrow keys, or click navigation buttons. 
                  Use the search feature to find specific departments or years.
                </p>
              </div>
              
              <div className="instruction-step">
                <h4>Download Results</h4>
                <p>
                  Export your timetables in Excel, PDF, or Image format using the 
                  download menu in the header. Each format is optimized for different 
                  use cases - sharing, printing, or archiving.
                </p>
              </div>
            </div>

            {/* Right Column - File Requirements */}
            <div className="requirements-panel">
              <div className="requirements-header">
                <h4>Excel File Requirements</h4>
                <p style={{ color: '#6b7280', fontSize: '0.9rem', margin: 0, lineHeight: 1.5 }}>
                  Your Excel file must contain the following columns with proper data formatting:
                </p>
              </div>

              <ul className="requirements-list">
                <li className="requirement-item">
                  <span className="requirement-label">Course Code</span>
                  <p className="requirement-description">
                    Unique identifier for each course (e.g., CSC101, MTH201)
                  </p>
                </li>
                
                <li className="requirement-item">
                  <span className="requirement-label">Course Title</span>
                  <p className="requirement-description">
                    Full descriptive name of the course
                  </p>
                </li>
                
                <li className="requirement-item">
                  <span className="requirement-label">Lecturer</span>
                  <p className="requirement-description">
                    Name of the instructor assigned to teach the course
                  </p>
                </li>
                
                <li className="requirement-item">
                  <span className="requirement-label">Duration</span>
                  <p className="requirement-description">
                    Length of each class session (in hours, e.g., 1, 2, 3)
                  </p>
                </li>
                
                <li className="requirement-item">
                  <span className="requirement-label">Level/Year</span>
                  <p className="requirement-description">
                    Academic year level (100, 200, 300, 400, etc.)
                  </p>
                </li>
                
                <li className="requirement-item">
                  <span className="requirement-label">Department</span>
                  <p className="requirement-description">
                    Academic department or faculty name
                  </p>
                </li>
                
                <li className="requirement-item">
                  <span className="requirement-label">Room Type</span>
                  <p className="requirement-description">
                    Preferred classroom type (Lecture Hall, Lab, etc.)
                  </p>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InstructionsModal;