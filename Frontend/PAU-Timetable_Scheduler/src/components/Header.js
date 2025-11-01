import React, { useState, useRef, useEffect } from 'react';
import './Header.css';
import Logo from '../assets/logo.png';

const Header = ({ onShowInstructions, onDownload, canDownload }) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleDownloadClick = (format) => {
    onDownload(format);
    setIsDropdownOpen(false);
  };

  return (
    <header className="header">
      <nav className="nav-container">
        <div className="logo-section">
          <img className="logo" src={Logo} alt='Logo'/>
          {/* <div className="university-name">Timetable Generator</div> */}
        </div>

        <div className="university-name">Timetable Generator</div>
        
        <div className="nav-right">
          <button 
            className="instructions-btn" 
            onClick={onShowInstructions}
            type="button"
          >
            How to Use
          </button>
          
          <div 
            className={`dropdown ${isDropdownOpen ? 'open' : ''}`}
            ref={dropdownRef}
          >
            <button 
              className={`dropdown-btn ${canDownload ? 'active' : ''}`}
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              disabled={!canDownload}
              type="button"
            >
              Download
              <span className="dropdown-arrow">▼</span>
            </button>
            <div className="dropdown-content">
              <button 
                className="dropdown-item" 
                onClick={() => handleDownloadClick('excel')}
                type="button"
              >
                📊 Excel Format
              </button>
              <button 
                className="dropdown-item" 
                onClick={() => handleDownloadClick('pdf')}
                type="button"
              >
                📄 PDF Format
              </button>
              <button 
                className="dropdown-item" 
                onClick={() => handleDownloadClick('image')}
                type="button"
              >
                🖼️ Image Format
              </button>
            </div>
          </div>
        </div>
      </nav>
    </header>
  );
};

export default Header;