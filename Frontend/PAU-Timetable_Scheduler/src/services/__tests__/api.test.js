import axios from 'axios';
import { uploadFile, generateTimetable, downloadTimetable } from '../api';

// Mock axios
jest.mock('axios');
const mockedAxios = axios;

// Mock environment variables
const originalEnv = process.env;

beforeEach(() => {
  jest.resetModules();
  process.env = {
    ...originalEnv,
    REACT_APP_API_BASE_URL: 'http://localhost:8000/api',
    REACT_APP_UPLOAD_ENDPOINT: '/timetable/upload',
    REACT_APP_GENERATE_ENDPOINT: '/timetable/generate',
    REACT_APP_DOWNLOAD_ENDPOINT: '/timetable/download'
  };
  
  // Reset axios mock
  mockedAxios.create.mockReturnValue(mockedAxios);
  mockedAxios.interceptors = {
    request: { use: jest.fn() },
    response: { use: jest.fn() }
  };
});

afterEach(() => {
  process.env = originalEnv;
  jest.clearAllMocks();
});

describe('API Service', () => {
  describe('uploadFile', () => {
    test('successfully uploads file', async () => {
      const mockResponse = {
        data: {
          fileId: 'test-file-id',
          filename: 'test.xlsx',
          status: 'uploaded'
        }
      };
      
      mockedAxios.post.mockResolvedValue(mockResponse);
      
      const file = new File(['test content'], 'test.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      });
      
      const result = await uploadFile(file);
      
      expect(mockedAxios.post).toHaveBeenCalledWith(
        '/timetable/upload',
        expect.any(FormData),
        expect.objectContaining({
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        })
      );
      
      expect(result).toEqual(mockResponse.data);
    });

    test('handles upload error', async () => {
      const error = new Error('Network Error');
      mockedAxios.post.mockRejectedValue(error);
      
      const file = new File(['test'], 'test.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      });
      
      await expect(uploadFile(file)).rejects.toThrow('File upload failed: Network Error');
    });
  });

  describe('generateTimetable', () => {
    test('successfully generates timetable', async () => {
      const mockResponse = {
        data: {
          timetables: [
            {
              title: 'Year 1 CS',
              department: 'Computer Science',
              level: '100 Level',
              courses: ['CSC101: Intro to Computing']
            }
          ],
          status: 'completed'
        }
      };
      
      mockedAxios.post.mockResolvedValue(mockResponse);
      
      const result = await generateTimetable('test-file-id');
      
      expect(mockedAxios.post).toHaveBeenCalledWith(
        '/timetable/generate',
        expect.objectContaining({
          fileId: 'test-file-id',
          options: expect.any(Object)
        }),
        expect.objectContaining({
          headers: {
            'Content-Type': 'application/json'
          }
        })
      );
      
      expect(result).toEqual(mockResponse.data);
    });

    test('calls progress callback', async () => {
      const mockResponse = { data: { timetables: [] } };
      const progressCallback = jest.fn();
      
      mockedAxios.post.mockResolvedValue(mockResponse);
      
      await generateTimetable('test-file-id', progressCallback);
      
      expect(mockedAxios.post).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Object),
        expect.objectContaining({
          onUploadProgress: expect.any(Function)
        })
      );
    });

    test('handles generation error', async () => {
      const error = new Error('Generation failed');
      mockedAxios.post.mockRejectedValue(error);
      
      await expect(generateTimetable('test-file-id')).rejects.toThrow('Timetable generation failed: Generation failed');
    });
  });

  describe('downloadTimetable', () => {
    test('successfully downloads timetable', async () => {
      const mockBlob = new Blob(['test content'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const mockResponse = { data: mockBlob };
      
      mockedAxios.post.mockResolvedValue(mockResponse);
      
      // Mock DOM methods
      const mockLink = {
        href: '',
        setAttribute: jest.fn(),
        click: jest.fn(),
        remove: jest.fn()
      };
      
      document.createElement = jest.fn().mockReturnValue(mockLink);
      document.body.appendChild = jest.fn();
      window.URL.createObjectURL = jest.fn().mockReturnValue('blob:test-url');
      window.URL.revokeObjectURL = jest.fn();
      
      const timetableData = [{ title: 'Test Timetable' }];
      
      await downloadTimetable(timetableData, 'excel');
      
      expect(mockedAxios.post).toHaveBeenCalledWith(
        '/timetable/download',
        expect.objectContaining({
          timetables: timetableData,
          format: 'excel'
        }),
        expect.objectContaining({
          responseType: 'blob'
        })
      );
      
      expect(document.createElement).toHaveBeenCalledWith('a');
      expect(mockLink.click).toHaveBeenCalled();
      expect(window.URL.revokeObjectURL).toHaveBeenCalled();
    });

    test('handles download error', async () => {
      const error = new Error('Download failed');
      mockedAxios.post.mockRejectedValue(error);
      
      const timetableData = [{ title: 'Test Timetable' }];
      
      await expect(downloadTimetable(timetableData, 'excel')).rejects.toThrow('Download failed: Download failed');
    });
  });
});