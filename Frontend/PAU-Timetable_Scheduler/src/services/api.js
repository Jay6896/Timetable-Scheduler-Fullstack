import axios from 'axios';

// Determine API base URL based on environment
const getApiBaseUrl = () => {
  // For development, use relative URLs to work with proxy
  if (process.env.NODE_ENV === 'development') {
    return '';
  }
  // Always prefer explicit env override if provided
  if (process.env.REACT_APP_API_BASE_URL) return process.env.REACT_APP_API_BASE_URL;
  // Default to local Flask backend
  return 'http://localhost:7860';
};

const API_BASE_URL = getApiBaseUrl();

// Create axios instance with CORS-friendly config
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minutes timeout for large file processing
  withCredentials: false, // Important for CORS
  headers: {
    'Accept': 'application/json',
    // Content-Type set conditionally in interceptor
  },
});

// Add request interceptor for logging and proper headers
apiClient.interceptors.request.use(
  (config) => {
    const method = (config.method || 'GET').toUpperCase();
    const url = config.baseURL ? `${config.baseURL}${config.url}` : config.url;
    console.log(`Making ${method} request to ${url}`);

    // Set appropriate headers for different request types
    if (config.data instanceof FormData) {
      // For file uploads, let browser set Content-Type with boundary
      if (config.headers) {
        delete config.headers['Content-Type'];
      }
    } else if (typeof config.data === 'object' && config.data !== null) {
      // For JSON data
      if (config.headers) {
        config.headers['Content-Type'] = 'application/json';
      }
    }

    // Do NOT set Access-Control-Allow-* on requests (these are response headers)
    return config;
  },
  (error) => {
    console.error('Request error:', error);
    return Promise.reject(error);
  }
);

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error);

    // Distinguish unreachable backend vs actual CORS rejection
    if (error.request && !error.response) {
      // Network error / connection refused
      if (error.code === 'ERR_NETWORK' || (error.message && error.message.includes('Network Error'))) {
        throw new Error('Cannot reach backend server. Ensure it is running and the API base URL is correct.');
      }
    }

    if (error.response) {
      const { status, data } = error.response;

      // Some browsers report CORS failures with opaque responses (status 0)
      if (status === 0) {
        throw new Error('CORS error: Backend did not allow this origin.');
      }

      const message = data?.message || data?.error || `Server error (${status})`;
      throw new Error(message);
    }

    // Fallback
    throw new Error(error.message || 'An unexpected error occurred');
  }
);

/**
 * Make a CORS-safe request with retry logic
 * @param {Function} requestFn - The axios request function
 * @param {number} retries - Number of retries
 */
const makeRequestWithRetry = async (requestFn, retries = 3) => {
  for (let i = 0; i < retries; i++) {
    try {
      return await requestFn();
    } catch (error) {
      if (i === retries - 1) throw error;

      const msg = error?.message || '';
      // If temporary network/CORS-like error, wait and retry
      if (msg.toLowerCase().includes('cors') || msg.toLowerCase().includes('backend') || msg.toLowerCase().includes('network')) {
        console.log(`Temporary connectivity error, retrying... (${i + 1}/${retries})`);
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
      } else {
        throw error;
      }
    }
  }
};

/**
 * Upload file to the server with CORS handling
 * @param {File} file - The Excel file to upload
 * @returns {Promise<Object>} Response containing file ID and metadata
 */
export const uploadFile = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('filename', file.name);

  const uploadEndpoint = process.env.REACT_APP_UPLOAD_ENDPOINT || '/upload-excel';

  try {
    const response = await makeRequestWithRetry(() =>
      apiClient.post(uploadEndpoint, formData)
    );

    const data = response.data;
    const uploadId = data.upload_id || data.uploadId || data.id; // defensive read
    if (!uploadId) throw new Error('upload_id not returned by server');

    console.log('Upload successful:', data);
    return { uploadId, meta: data };
  } catch (err) {
    console.error('Upload error details:', err);
    const message = err?.response?.data?.error || err.message || 'Upload failed';
    throw new Error(`File upload failed: ${message}`);
  }
};

/**
 * Generate timetable from uploaded file
 * @param {string} uploadId - ID of the uploaded file
 * @param {Function} progressCallback - Callback for progress updates
 * @param {Object} options - Optional parameters to override defaults (e.g., max_generations)
 * @returns {Promise<Object>} Generated timetable data
 */
export const generateTimetable = async (uploadId, progressCallback, options) => {
  try {
    // Start the generation process
    const body = {
      upload_id: uploadId,
      config: {
        population_size: Number(process.env.REACT_APP_DE_POP_SIZE) || 25,
        max_generations: Number(process.env.REACT_APP_DE_MAX_GENS) || 10,
        F: Number(process.env.REACT_APP_DE_F) || 0.4,
        CR: Number(process.env.REACT_APP_DE_CR) || 0.9
      }
    };

    // Allow overrides from caller (e.g., user-provided generations)
    if (options && typeof options === 'object') {
      body.config = { ...body.config, ...options };
    }

    console.log('Starting timetable generation with:', body);
    const startResponse = await makeRequestWithRetry(() =>
      apiClient.post('/generate-timetable', body)
    );

    if (startResponse.status !== 202) {
      throw new Error('Failed to start timetable generation');
    }

    console.log('Generation started, polling for status...');
    // Poll for status updates
    return await pollForCompletion(uploadId, progressCallback);

  } catch (error) {
    console.error('Generation error:', error);
    const msg = error?.response?.data?.error || error?.message || 'Unknown error';
    throw new Error(`Timetable generation failed: ${msg}`);
  }
};

/**
 * Poll the server for generation completion status with CORS handling
 * @param {string} uploadId - Upload ID to check status for
 * @param {Function} progressCallback - Progress update callback
 * @returns {Promise<Object>} Final timetable data
 */
const pollForCompletion = async (uploadId, progressCallback) => {
  const maxAttempts = 120; // 10 minutes with 5-second intervals
  let attempts = 0;

  return new Promise((resolve, reject) => {
    const checkStatus = async () => {
      try {
        attempts++;
        const statusResponse = await makeRequestWithRetry(() =>
          apiClient.get(`/get-timetable-status/${uploadId}`)
        );
        const statusData = statusResponse && statusResponse.data ? statusResponse.data : {};

        // Normalize status and derive sensible defaults
        const normalized = {
          status: statusData.status || statusData.State || statusData.state,
          progress: typeof statusData.progress === 'number' ? statusData.progress : 0,
          message: statusData.message || '',
          result: statusData.result,
          error: statusData.error || statusData.Error
        };

        // If backend returned a completed result but no explicit status
        if (!normalized.status && normalized.result) {
          normalized.status = 'completed';
        }
        // If backend indicates error but no explicit status
        if (!normalized.status && normalized.error) {
          normalized.status = 'error';
        }
        // Default to processing if still undefined but HTTP 200
        if (!normalized.status) {
          normalized.status = 'processing';
        }

        // Update progress UI
        if (progressCallback) {
          progressCallback({
            percentage: normalized.progress,
            message: normalized.message || 'Processing...'
          });
        }

        if (normalized.status === 'completed') {
          const result = normalized.result;
          if (result) {
            if (!result.timetables && result.timetables_raw) {
              result.timetables = result.timetables_raw;
            }
            if (result.parsed_timetables && result.timetables) {
              result.timetables = result.timetables.map((timetable, index) => {
                const parsed = result.parsed_timetables[index];
                return { ...timetable, rows: parsed ? parsed.rows : [] };
              });
            }
          }
          // ensure UI reflects completion
          if (progressCallback) {
            progressCallback({ percentage: 100, message: 'Completed' });
          }
          resolve(result);
          return;
        }

        if (normalized.status === 'error') {
          reject(new Error(normalized.error || 'Generation failed'));
          return;
        }

        // Still processing, continue polling
        if (attempts >= maxAttempts) {
          reject(new Error('Generation timeout - please try again'));
          return;
        }
        setTimeout(checkStatus, 5000);
        return;
      } catch (error) {
        console.error('Status check error:', error);
        if (error.message.includes('CORS')) {
          reject(new Error('CORS policy is blocking requests to the backend. Please check the server configuration.'));
        } else {
          reject(error);
        }
      }
    };

    // Start polling
    checkStatus();
  });
};

/**
 * Download generated timetable in specified format with CORS handling
 * @param {string} uploadId - The upload ID from the generation process
 * @param {string} format - Download format ('excel', 'pdf')
 * @returns {Promise<void>}
 */
export const downloadTimetable = async (uploadId, format) => {
  try {
    console.log(`Downloading timetable: ${uploadId} in ${format} format`);
    const response = await makeRequestWithRetry(() =>
      apiClient.post(
        '/export-timetable',
        {
          upload_id: uploadId,
          format: format.toLowerCase()
        },
        {
          responseType: 'blob', // Important for file downloads
        }
      )
    );

    // Create blob link to download
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    
    // Set filename based on format
    const timestamp = new Date().toISOString().slice(0, 10);
    const filename = `timetable_${timestamp}.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
    link.setAttribute('download', filename);
    
    // Trigger download
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
    
  } catch (error) {
    console.error('Download error:', error);
    throw new Error(`Download failed: ${error.message}`);
  }
};

/**
 * Get available time slots from server
 * @returns {Promise<Array>} Available time slots
 */
export const getTimeSlots = async () => {
  try {
    // Try to get time slots from API first
    const response = await makeRequestWithRetry(() =>
      apiClient.get('/timetable/timeslots')
    );
    return response.data;
  } catch (error) {
    // If API endpoint doesn't exist or fails, return default time slots
    console.warn('Failed to fetch time slots from API, using defaults:', error.message);
    return [
      { start: '09:00', end: '10:00', label: '9:00 AM' },
      { start: '10:00', end: '11:00', label: '10:00 AM' },
      { start: '11:00', end: '12:00', label: '11:00 AM' },
      { start: '12:00', end: '13:00', label: '12:00 PM' },
      { start: '14:00', end: '15:00', label: '2:00 PM' },
      { start: '15:00', end: '16:00', label: '3:00 PM' },
      { start: '16:00', end: '17:00', label: '4:00 PM' },
    ];
  }
};

/**
 * Validate uploaded file on server
 * @param {string} fileId - ID of uploaded file
 * @returns {Promise<Object>} Validation results
 */
export const validateFile = async (fileId) => {
  try {
    const response = await makeRequestWithRetry(() =>
      apiClient.post('/timetable/validate', { fileId })
    );
    return response.data;
  } catch (error) {
    throw new Error(`File validation failed: ${error.message}`);
  }
};

/**
 * Utilities to work with the backend Dash UI mounted under /interactive
 */
export const getBackendBaseUrl = () => API_BASE_URL;

export const getDashUrl = (uploadId) => {
  // The Dash app reads the latest generated data saved by the backend.
  // Attach the job id as a query param for visibility (Dash ignores it, harmless).
  const base = `${API_BASE_URL}/interactive/`;
  return uploadId ? `${base}?job=${encodeURIComponent(uploadId)}` : base;
};

export const openDashUI = (uploadId) => {
  const url = getDashUrl(uploadId);
  try {
    window.open(url, '_blank', 'noopener,noreferrer');
  } catch (_) {
    // Fallback
    window.location.href = url;
  }
};

export default apiClient;
