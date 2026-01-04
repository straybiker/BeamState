import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import Config from './components/Config';
import Discovery from './components/Discovery';

import MetricsDashboard from './components/MetricsDashboard';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/metrics" element={<MetricsDashboard />} />
          <Route path="/config" element={<Config />} />
          <Route path="/discovery" element={<Discovery />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
