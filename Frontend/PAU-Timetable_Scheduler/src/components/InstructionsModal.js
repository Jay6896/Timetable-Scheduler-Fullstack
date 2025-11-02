import React, { useEffect, useRef, useState } from 'react';
import './InstructionsModal.css';

const InstructionsModal = ({ isOpen, onClose }) => {
  const modalRef = useRef(null);
  const closeButtonRef = useRef(null);
  const [activeTab, setActiveTab] = useState('uploading');

  useEffect(() => {
    if (isOpen) {
      // Focus the close button when modal opens
      if (closeButtonRef.current) {
        closeButtonRef.current.focus();
      }
      
      // Add body class to prevent scrolling
      document.body.classList.add('modal-open');
      
      // Handle escape key
      const handleEscape = (e) => {
        if (e.key === 'Escape') {
          onClose();
        }
      };
      
      document.addEventListener('keydown', handleEscape);
      
      return () => {
        document.removeEventListener('keydown', handleEscape);
        document.body.classList.remove('modal-open');
      };
    }
  }, [isOpen, onClose]);

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleDownloadTemplate = () => {
    // Create a link to download the template file
    const link = document.createElement('a');
    link.href = '/api/download-template'; // This would need to be implemented in your backend
    link.download = 'Timetable_Input_Template.xlsx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!isOpen) return null;

  return (
    <div className="modal" onClick={handleOverlayClick}>
      <div className="modal-content" ref={modalRef} tabIndex="-1">
        <div className="modal-header">
          <h2 className="modal-title">How to Use PAU Timetable Scheduler</h2>
          <button 
            className="close-btn" 
            onClick={onClose}
            ref={closeButtonRef}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>
        
        <div className="modal-body">
          <div className="tab-navigation">
            <button 
              className={`tab-button ${activeTab === 'uploading' ? 'active' : ''}`}
              onClick={() => setActiveTab('uploading')}
            >
              Uploading Files
            </button>
            <button 
              className={`tab-button ${activeTab === 'requirements' ? 'active' : ''}`}
              onClick={() => setActiveTab('requirements')}
            >
              Input File Requirements
            </button>
          </div>

          <div className="tab-content">
            {activeTab === 'uploading' && (
              <div className="uploading-tab">
                <div className="instruction-step">
                  <h4>1. Prepare Your Excel File</h4>
                  <p>Download our template file or ensure your Excel file follows the required format with the exact sheet names and column headers.</p>
                </div>
                
                <div className="instruction-step">
                  <h4>2. Upload Your File</h4>
                  <p>Click the "Choose File" button in the File Upload section and select your Excel file (.xlsx format only).</p>
                </div>
                
                <div className="instruction-step">
                  <h4>3. Wait for Processing</h4>
                  <p>The system will validate and parse your Excel file. Watch the progress bar for upload status.</p>
                </div>
                
                <div className="instruction-step">
                  <h4>4. Generate Timetable</h4>
                  <p>Once uploaded successfully, click "Generate Timetable" to create an optimized schedule using our genetic algorithm.</p>
                </div>
                
                <div className="instruction-step">
                  <h4>5. View Your Timetable</h4>
                  <p>Choose how to view your generated timetable:</p>
                  <ul>
                    <li><strong>View in iframe:</strong> See the timetable embedded in this page</li>
                    <li><strong>Open in new tab:</strong> Open the interactive timetable in a separate browser tab for full-screen viewing</li>
                  </ul>
                </div>
                
                <div className="instruction-step">
                  <h4>6. Interact with Your Timetable</h4>
                  <p>In the interactive view, you can:</p>
                  <ul>
                    <li>Drag and drop classes to different time slots</li>
                    <li>View constraint conflicts highlighted in red</li>
                    <li>Switch between different generated solutions</li>
                    <li>Export your final timetable</li>
                  </ul>
                </div>
              </div>
            )}

            {activeTab === 'requirements' && (
              <div className="requirements-tab">
                <div className="template-download">
                  <h4>📁 Download Template File</h4>
                  <p>Use our pre-formatted template to ensure compatibility:</p>
                  <button className="download-template-btn" onClick={handleDownloadTemplate}>
                    📥 Download Timetable_Input_Template.xlsx
                  </button>
                </div>

                <div className="sheet-requirements">
                  <h4>📋 Required Excel Sheets</h4>
                  <p>Your Excel file must contain exactly these 4 sheets with these exact names:</p>
                  
                  <div className="sheet-list">
                    <div className="sheet-item">
                      <h5>1. Courses</h5>
                      <p>Contains course information with columns: Course Code, Course Name, Credits, Duration</p>
                    </div>
                    
                    <div className="sheet-item">
                      <h5>2. Faculty</h5>
                      <p>Contains faculty information with columns: Faculty ID, Faculty Name, Department, Available Days</p>
                    </div>
                    
                    <div className="sheet-item">
                      <h5>3. Student Groups</h5>
                      <p>Contains student group information with columns: Group ID, Group Name, Year, Semester, Size</p>
                    </div>
                    
                    <div className="sheet-item">
                      <h5>4. Rooms</h5>
                      <p>Contains room information with columns: Room ID, Room Name, Capacity, Type, Equipment</p>
                    </div>
                  </div>
                </div>

                <div className="format-examples">
                  <h4>📊 Format Examples</h4>
                  <p>Required column structure for each sheet:</p>
                  
                  <div className="format-tables">
                    <div className="format-table">
                      <h5>Courses Sheet</h5>
                      <table className="example-table">
                        <thead>
                          <tr>
                            <th>Course Code</th>
                            <th>Course Name</th>
                            <th>Credits</th>
                            <th>Duration</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>CSC101</td>
                            <td>Introduction to Programming</td>
                            <td>3</td>
                            <td>2</td>
                          </tr>
                          <tr>
                            <td>MTH201</td>
                            <td>Calculus II</td>
                            <td>4</td>
                            <td>3</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    
                    <div className="format-table">
                      <h5>Faculty Sheet</h5>
                      <table className="example-table">
                        <thead>
                          <tr>
                            <th>Faculty ID</th>
                            <th>Faculty Name</th>
                            <th>Department</th>
                            <th>Available Days</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>F001</td>
                            <td>Dr. Smith</td>
                            <td>Computer Science</td>
                            <td>Mon,Tue,Wed,Thu,Fri</td>
                          </tr>
                          <tr>
                            <td>F002</td>
                            <td>Prof. Johnson</td>
                            <td>Mathematics</td>
                            <td>Mon,Wed,Fri</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    
                    <div className="format-table">
                      <h5>Student Groups Sheet</h5>
                      <table className="example-table">
                        <thead>
                          <tr>
                            <th>Group ID</th>
                            <th>Group Name</th>
                            <th>Year</th>
                            <th>Semester</th>
                            <th>Size</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>G001</td>
                            <td>CS Year 1 Group A</td>
                            <td>1</td>
                            <td>1</td>
                            <td>30</td>
                          </tr>
                          <tr>
                            <td>G002</td>
                            <td>Math Year 2 Group B</td>
                            <td>2</td>
                            <td>1</td>
                            <td>25</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    
                    <div className="format-table">
                      <h5>Rooms Sheet</h5>
                      <table className="example-table">
                        <thead>
                          <tr>
                            <th>Room ID</th>
                            <th>Room Name</th>
                            <th>Capacity</th>
                            <th>Type</th>
                            <th>Equipment</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>R001</td>
                            <td>Lecture Hall A</td>
                            <td>50</td>
                            <td>Lecture</td>
                            <td>Projector,Audio</td>
                          </tr>
                          <tr>
                            <td>R002</td>
                            <td>Computer Lab 1</td>
                            <td>30</td>
                            <td>Lab</td>
                            <td>Computers,Projector</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                <div className="important-notes">
                  <h4>⚠️ Important Notes</h4>
                  <ul>
                    <li><strong>Column names must match exactly</strong> - case sensitive</li>
                    <li><strong>Sheet names must be exactly:</strong> "Courses", "Faculty", "Student Groups", "Rooms"</li>
                    <li><strong>File format:</strong> .xlsx only (not .xls or .csv)</li>
                    <li><strong>No empty rows</strong> between headers and data</li>
                    <li><strong>UTF-8 encoding</strong> recommended for special characters</li>
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default InstructionsModal;