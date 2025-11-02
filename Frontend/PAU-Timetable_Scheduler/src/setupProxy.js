const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  // Proxy specific API endpoints to backend
  const apiPaths = [
    '/upload-excel',
    '/generate-timetable', 
    '/get-timetable-status',
    '/export-timetable',
    '/api/download-template'
  ];
  
  apiPaths.forEach(path => {
    app.use(
      path,
      createProxyMiddleware({
        target: 'http://localhost:7860',
        changeOrigin: true,
      })
    );
  });
  
  // Proxy interactive routes for Dash UI
  app.use(
    '/interactive',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
    })
  );
  
  // Proxy Dash-specific routes
  app.use(
    '/_dash',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
    })
  );
  
  // Proxy other backend assets
  app.use(
    '/assets',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
    })
  );
};
