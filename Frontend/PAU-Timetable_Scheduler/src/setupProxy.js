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
        ws: false,
      })
    );
  });
  
  // Proxy interactive routes for Dash UI (covers /interactive/* including assets & _dash*)
  app.use(
    '/interactive',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
      ws: false,
    })
  );
  
  // Proxy Dash core endpoints that some Dash versions emit without prefix
  app.use(
    '/_dash-component-suites',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
      ws: false,
    })
  );
  app.use(
    '/_dash-layout',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
      ws: false,
    })
  );
  app.use(
    '/_dash-dependencies',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
      ws: false,
    })
  );
  app.use(
    '/_dash-update-component',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
      ws: false,
    })
  );
  app.use(
    '/_favicon.ico',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
      ws: false,
    })
  );

  // Proxy other backend assets
  app.use(
    '/assets',
    createProxyMiddleware({
      target: 'http://localhost:7860',
      changeOrigin: true,
      ws: false,
    })
  );
};
