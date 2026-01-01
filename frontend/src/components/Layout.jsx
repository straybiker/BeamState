import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Activity, Settings, Server } from 'lucide-react';

const Layout = ({ children }) => {
    const location = useLocation();

    const navItems = [
        { name: 'Dashboard', path: '/', icon: Activity },
        { name: 'SNMP Metrics', path: '/metrics', icon: Server },
        { name: 'Configuration', path: '/config', icon: Settings },
    ];

    return (
        <div className="min-h-screen flex flex-col md:flex-row">
            {/* Sidebar / Mobile Header */}
            <nav className="bg-surface p-4 md:w-64 md:h-screen flex md:flex-col justify-between items-center md:items-stretch border-r border-slate-700 shadow-lg z-10">
                <div className="flex items-center space-x-2 mb-0 md:mb-8">
                    <img src="/logo_transparant.png" alt="Logo" className="h-10 object-contain" />
                    <div>
                        <h1 className="text-xl font-bold tracking-wider text-primary">BeamState</h1>
                        <span className="text-xs text-slate-500 block uppercase tracking-widest" style={{ fontSize: '0.6rem' }}>Network Monitoring</span>
                    </div>
                </div>

                <div className="flex md:flex-col space-x-4 md:space-x-0 md:space-y-2">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const active = location.pathname === item.path;
                        return (
                            <Link
                                key={item.name}
                                to={item.path}
                                className={`flex items-center space-x-2 px-4 py-3 rounded-lg transition-colors ${active
                                    ? 'bg-primary/20 text-blue-300'
                                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                                    }`}
                            >
                                <Icon size={20} />
                                <span className="hidden md:inline font-medium">{item.name}</span>
                            </Link>
                        );
                    })}
                </div>
            </nav>

            {/* Main Content */}
            <main className="flex-1 p-4 md:p-8 overflow-y-auto">
                <div className="max-w-6xl mx-auto">
                    {children}
                </div>
            </main>
        </div>
    );
};

export default Layout;
