import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import TimetableGenerator from '../TimetableGenerator';
import * as api from '../../services/api';

// Mock the API module
jest.mock('../../services/api');

describe('TimetableGenerator', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders main components', () => {
    render(<TimetableGenerator />);
    
    expect(screen.getByText('Pan-Atlantic University')).toBeInTheDocument();
    expect(screen.getByText('File Upload & Processing')).toBeInTheDocument();
    expect(screen.getByText('How to Use')).toBeInTheDocument();
  });

  test('shows instructions modal when button is clicked', () => {
    render(<TimetableGenerator />);
    
    const instructionsBtn = screen.getByText('How to Use');
    fireEvent.click(instructionsBtn);
    
    expect(screen.getByText('How to Use the Timetable Generator')).toBeInTheDocument();
    expect(screen.getByText('Step 1: Upload Excel File')).toBeInTheDocument();
  });

  test('closes instructions modal when close button is clicked', () => {
    render(<TimetableGenerator />);
    
    // Open modal
    const instructionsBtn = screen.getByText('How to Use');
    fireEvent.click(instructionsBtn);
    
    // Close modal
    const closeBtn = screen.getByLabelText('Close modal');
    fireEvent.click(closeBtn);
    
    expect(screen.queryByText('How to Use the Timetable Generator')).not.toBeInTheDocument();
  });

  test('handles file selection', () => {
    render(<TimetableGenerator />);
    
    const fileInput = screen.getByLabelText('Browse...');
    const file = new File(['test content'], 'test.xlsx', { 
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
    });
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    expect(screen.getByDisplayValue('test.xlsx')).toBeInTheDocument();
    expect(screen.getByText(/File loaded: test.xlsx/)).toBeInTheDocument();
    expect(screen.getByText('Generate Timetable')).toBeInTheDocument();
  });

  test('handles file reset', () => {
    render(<TimetableGenerator />);
    
    // Select a file
    const fileInput = screen.getByLabelText('Browse...');
    const file = new File(['test content'], 'test.xlsx', { 
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
    });
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    // Reset
    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);
    
    expect(screen.getByPlaceholderText('No file selected...')).toHaveValue('');
    expect(screen.queryByText(/File loaded/)).not.toBeInTheDocument();
  });

  test('handles successful timetable generation', async () => {
    // Mock API responses
    api.uploadFile.mockResolvedValue({ fileId: 'test-file-id' });
    api.generateTimetable.mockResolvedValue({
      timetables: [
        {
          title: 'Year 1 Computer Science',
          department: 'Computer Science',
          level: '100 Level',
          courses: ['CSC101: Intro to Computing']
        }
      ]
    });

    render(<TimetableGenerator />);
    
    // Select a file
    const fileInput = screen.getByLabelText('Browse...');
    const file = new File(['test content'], 'test.xlsx', { 
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
    });
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    // Generate timetable
    const generateBtn = screen.getByText('Generate Timetable');
    fireEvent.click(generateBtn);
    
    // Wait for results
    await waitFor(() => {
      expect(screen.getByText('Generated Timetables')).toBeInTheDocument();
      expect(screen.getByText('Year 1 Computer Science')).toBeInTheDocument();
    });
  });

  test('handles API errors during generation', async () => {
    // Mock API error
    api.uploadFile.mockRejectedValue(new Error('Upload failed'));

    render(<TimetableGenerator />);
    
    // Select a file
    const fileInput = screen.getByLabelText('Browse...');
    const file = new File(['test content'], 'test.xlsx', { 
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
    });
    
    fireEvent.change(fileInput, { target: { files: [file] } });
    
    // Generate timetable
    const generateBtn = screen.getByText('Generate Timetable');
    fireEvent.click(generateBtn);
    
    // Wait for error
    await waitFor(() => {
      expect(screen.getByText(/Error: Upload failed/)).toBeInTheDocument();
    });
  });

  test('download button is disabled when no timetables are generated', () => {
    render(<TimetableGenerator />);
    
    const downloadBtn = screen.getByText('Download');
    expect(downloadBtn).toBeDisabled();
  });
});