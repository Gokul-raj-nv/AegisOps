import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import IncidentDetail from './pages/IncidentDetail';
import './index.css';

function Navbar() {
  return (
    <nav className="navbar">
      <NavLink to="/" className="navbar-brand">
        <div className="navbar-logo">A</div>
        <div>
          <div>AegisOps</div>
          <div className="navbar-tagline">AI Incident Response Platform</div>
        </div>
      </NavLink>
      <div className="navbar-actions">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          <div className="status-dot" />
          System operational
        </div>
        <NavLink to="/" className={({ isActive }) =>
          `btn btn-outline btn-sm ${isActive ? 'btn-primary' : ''}`
        } end>
          Dashboard
        </NavLink>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Navbar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
