
import React, { useState, useEffect } from 'react';
import { Save, RefreshCw, Database, FileText } from 'lucide-react';
import { toast } from 'react-hot-toast';
import api from '../api';

const AppConfig = () => {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadConfig();
    }, []);

    const loadConfig = async () => {
        try {
            setLoading(true);
            const response = await api.get('/config/app');
            setConfig(response.data);
        } catch (error) {
            console.error("Failed to load app config:", error);
            toast.error("Failed to load settings");
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        try {
            setSaving(true);
            const response = await api.put('/config/app', config);
            setConfig(response.data);
            toast.success("Settings saved successfully");
        } catch (error) {
            console.error("Failed to save settings:", error);
            toast.error("Failed to save settings");
        } finally {
            setSaving(false);
        }
    };

    const handleChange = (section, field, value) => {
        setConfig(prev => ({
            ...prev,
            [section]: {
                ...prev[section],
                [field]: value
            }
        }));
    };

    if (loading) {
        return <div className="text-center p-8 text-slate-400">Loading settings...</div>;
    }

    if (!config) {
        return <div className="text-center p-8 text-red-400">Failed to load configuration.</div>;
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-xl font-bold text-white">Application Settings</h2>
                    <p className="text-sm text-slate-400">Configure global application behavior</p>
                </div>
                <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex items-center space-x-2 bg-primary hover:bg-primary/90 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
                >
                    {saving ? <RefreshCw className="animate-spin" size={18} /> : <Save size={18} />}
                    <span>Save Changes</span>
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* InfluxDB Configuration */}
                <div className="bg-surface rounded-xl p-6 border border-slate-700/50">
                    <div className="flex items-center space-x-3 mb-4">
                        <div className="p-2 bg-purple-500/20 text-purple-400 rounded-lg">
                            <Database size={24} />
                        </div>
                        <h3 className="text-lg font-semibold text-white">InfluxDB Storage</h3>
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center space-x-2">
                            <input
                                type="checkbox"
                                id="influx-enabled"
                                checked={config.influxdb.enabled}
                                onChange={(e) => handleChange('influxdb', 'enabled', e.target.checked)}
                                className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-primary focus:ring-primary"
                            />
                            <label htmlFor="influx-enabled" className="text-sm font-medium text-slate-200">
                                Enable InfluxDB Integration
                            </label>
                        </div>

                        <div className="space-y-1">
                            <label className="text-xs text-slate-400 uppercase font-bold tracking-wider">URL</label>
                            <input
                                type="text"
                                value={config.influxdb.url}
                                onChange={(e) => handleChange('influxdb', 'url', e.target.value)}
                                placeholder="http://localhost:8086"
                                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary focus:outline-none"
                            />
                        </div>

                        <div className="space-y-1">
                            <label className="text-xs text-slate-400 uppercase font-bold tracking-wider">Organization</label>
                            <input
                                type="text"
                                value={config.influxdb.org}
                                onChange={(e) => handleChange('influxdb', 'org', e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary focus:outline-none"
                            />
                        </div>

                        <div className="space-y-1">
                            <label className="text-xs text-slate-400 uppercase font-bold tracking-wider">Bucket</label>
                            <input
                                type="text"
                                value={config.influxdb.bucket}
                                onChange={(e) => handleChange('influxdb', 'bucket', e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary focus:outline-none"
                            />
                        </div>

                        <div className="space-y-1">
                            <label className="text-xs text-slate-400 uppercase font-bold tracking-wider">Token</label>
                            <input
                                type="password"
                                value={config.influxdb.token}
                                onChange={(e) => handleChange('influxdb', 'token', e.target.value)}
                                placeholder="Start with a standard token..."
                                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary focus:outline-none font-mono"
                            />
                        </div>
                    </div>
                </div>

                {/* Monitoring Data Logs Configuration */}
                <div className="bg-surface rounded-xl p-6 border border-slate-700/50">
                    <div className="flex items-center space-x-3 mb-4">
                        <div className="p-2 bg-blue-500/20 text-blue-400 rounded-lg">
                            <FileText size={24} />
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold text-white">Monitoring Data Logs</h3>
                            <p className="text-xs text-slate-400">Store monitoring results to JSON file</p>
                        </div>
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center space-x-2">
                            <input
                                type="checkbox"
                                id="logging-enabled"
                                checked={config.logging.file_enabled}
                                onChange={(e) => handleChange('logging', 'file_enabled', e.target.checked)}
                                className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-primary focus:ring-primary"
                            />
                            <label htmlFor="logging-enabled" className="text-sm font-medium text-slate-200">
                                Enable Monitoring Data Logging
                            </label>
                        </div>

                        <div className="space-y-1">
                            <label className="text-xs text-slate-400 uppercase font-bold tracking-wider">Log File Path</label>
                            <input
                                type="text"
                                value={config.logging.file_path}
                                onChange={(e) => handleChange('logging', 'file_path', e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary focus:outline-none font-mono"
                            />
                            <p className="text-xs text-slate-500">Relative to backend/ directory unless absolute.</p>
                        </div>

                        <div className="space-y-1">
                            <label className="text-xs text-slate-400 uppercase font-bold tracking-wider">Retention (Lines)</label>
                            <input
                                type="number"
                                value={config.logging.retention_lines}
                                onChange={(e) => handleChange('logging', 'retention_lines', parseInt(e.target.value))}
                                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary focus:outline-none"
                            />
                            <p className="text-xs text-slate-500">Maximum lines to keep in the log file.</p>
                        </div>
                    </div>
                </div>

                {/* System Logs Configuration */}
                <div className="bg-surface rounded-xl p-6 border border-slate-700/50">
                    <div className="flex items-center space-x-3 mb-4">
                        <div className="p-2 bg-green-500/20 text-green-400 rounded-lg">
                            <FileText size={24} />
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold text-white">System Logs</h3>
                            <p className="text-xs text-slate-400">Application events (always enabled)</p>
                        </div>
                    </div>

                    <div className="space-y-4">
                        <div className="bg-slate-900/50 border border-slate-700 rounded p-3">
                            <p className="text-sm text-slate-300">
                                System logs are always written to <code className="text-primary font-mono text-xs">backend/system.log</code>
                            </p>
                            <p className="text-xs text-slate-500 mt-2">
                                Contains startup events, warnings, errors, and monitoring activity based on log level.
                            </p>
                        </div>

                        <div className="space-y-1">
                            <label className="text-xs text-slate-400 uppercase font-bold tracking-wider">System Log Level</label>
                            <select
                                value={config.logging.log_level || 'INFO'}
                                onChange={(e) => handleChange('logging', 'log_level', e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary focus:outline-none"
                            >
                                <option value="DEBUG">DEBUG - Verbose (includes all monitoring results)</option>
                                <option value="INFO">INFO - Standard (startup, warnings, errors)</option>
                                <option value="WARNING">WARNING - Warnings and errors only</option>
                                <option value="ERROR">ERROR - Errors only</option>
                            </select>
                            <p className="text-xs text-slate-500">⚠️ Requires application restart to take effect.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AppConfig;
