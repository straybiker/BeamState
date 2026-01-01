import React, { useState, useEffect } from 'react';
import api from '../api';
import { Save, RefreshCw, Check, AlertCircle, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';

const MetricsConfig = ({ nodes, groups = [] }) => {
    const [selectedNodeId, setSelectedNodeId] = useState('');
    const [interfaces, setInterfaces] = useState([]);
    const [definitions, setDefinitions] = useState([]);
    const [nodeMetrics, setNodeMetrics] = useState([]); // Currently saved metrics

    // UI Selection State
    const [loadingInterfaces, setLoadingInterfaces] = useState(false);
    const [saving, setSaving] = useState(false);

    // Staging state for new configuration
    const [selectedSystemMetrics, setSelectedSystemMetrics] = useState(new Set());
    const [selectedInterfaceMetrics, setSelectedInterfaceMetrics] = useState(new Set());
    const [selectedInterfaces, setSelectedInterfaces] = useState(new Set());

    // Filter nodes specific to SNMP
    const snmpNodes = nodes.filter(n => {
        if (n.monitor_snmp === true) return true;
        if (n.monitor_snmp === false) return false;
        // Fallback to group
        const group = groups.find(g => g.id === n.group_id);
        return group ? group.monitor_snmp : false;
    });

    // Load metric definitions on mount
    useEffect(() => {
        const loadDefinitions = async () => {
            try {
                const res = await api.get('/metrics/definitions');
                setDefinitions(res.data);
            } catch (e) {
                console.error("Failed to load metric definitions", e);
                toast.error("Could not load available metrics");
            }
        };
        loadDefinitions();
    }, []);

    // Load node details when selected
    useEffect(() => {
        if (!selectedNodeId) {
            setInterfaces([]);
            setNodeMetrics([]);
            setSelectedSystemMetrics(new Set());
            setSelectedInterfaceMetrics(new Set());
            setSelectedInterfaces(new Set());
            return;
        }

        loadNodeConfiguration(selectedNodeId);
    }, [selectedNodeId]);

    const loadNodeConfiguration = async (nodeId) => {
        try {
            // Load existing configured metrics
            const res = await api.get(`/metrics/nodes/${nodeId}`);
            const metrics = res.data;
            setNodeMetrics(metrics);

            // Populate selection state from existing config
            const sysMetrics = new Set();
            const ifMetrics = new Set();
            const ifaces = new Set();

            metrics.forEach(m => {
                const def = definitions.find(d => d.id === m.metric_definition_id);
                if (!def) return;

                if (def.category === 'interface') {
                    ifMetrics.add(def.id);
                    if (m.interface_index) {
                        // Store detailed interface info if possible, but for Set we just store index
                        ifaces.add(m.interface_index);
                    }
                } else {
                    sysMetrics.add(def.id);
                }
            });

            setSelectedSystemMetrics(sysMetrics);
            setSelectedInterfaceMetrics(ifMetrics);
            setSelectedInterfaces(ifaces);

        } catch (e) {
            console.error(e);
            toast.error("Failed to load node configuration");
        }
    };

    const handleDiscoverInterfaces = async () => {
        if (!selectedNodeId) return;
        setLoadingInterfaces(true);
        try {
            const res = await api.get(`/metrics/discover-interfaces/${selectedNodeId}`);
            setInterfaces(res.data);
            toast.success(`Found ${res.data.length} interfaces`);
        } catch (err) {
            console.error(err);
            let message = "Discovery failed. Check SNMP settings.";
            if (err.response?.data?.detail) {
                message = `Error: ${err.response.data.detail}`;
            }
            toast.error(message);
        } finally {
            setLoadingInterfaces(false);
        }
    };

    const handleSave = async () => {
        if (!selectedNodeId) return;
        setSaving(true);

        try {
            const payload = [];

            // System Metrics
            selectedSystemMetrics.forEach(defId => {
                payload.push({
                    node_id: selectedNodeId,
                    metric_definition_id: defId,
                    collection_interval: 60, // Default for now
                    enabled: true
                });
            });

            // Interface Metrics
            // Must apply every selected interface metric to every selected interface
            if (selectedInterfaceMetrics.size > 0 && selectedInterfaces.size > 0) {
                selectedInterfaceMetrics.forEach(defId => {
                    selectedInterfaces.forEach(ifIndex => {
                        // Find interface name from discovery list if available
                        const iface = interfaces.find(i => i.index === ifIndex);
                        const ifName = iface ? iface.name : `Index ${ifIndex}`;

                        payload.push({
                            node_id: selectedNodeId,
                            metric_definition_id: defId,
                            interface_index: ifIndex,
                            interface_name: ifName,
                            collection_interval: 60,
                            enabled: true
                        })
                    });
                });
            }

            await api.post(`/metrics/nodes/${selectedNodeId}`, payload);
            toast.success("Metrics configuration saved");

            // Reload to confirm
            loadNodeConfiguration(selectedNodeId);

        } catch (e) {
            console.error(e);
            toast.error("Failed to save configuration");
        } finally {
            setSaving(false);
        }
    };

    // Helper to toggle set items
    const toggleSet = (setObj, updateFunc, item) => {
        const newSet = new Set(setObj);
        if (newSet.has(item)) newSet.delete(item);
        else newSet.add(item);
        updateFunc(newSet);
    };

    const toggleAllInterfaces = () => {
        if (selectedInterfaces.size === interfaces.length) {
            setSelectedInterfaces(new Set());
        } else {
            setSelectedInterfaces(new Set(interfaces.map(i => i.index)));
        }
    };

    const sysDefs = definitions.filter(d => d.category !== 'interface');
    const ifDefs = definitions.filter(d => d.category === 'interface');

    return (
        <div className="bg-surface p-6 rounded-xl border border-slate-700 shadow-sm space-y-6">
            <h3 className="text-xl font-semibold text-slate-100 flex items-center">
                SNMP Metrics Configuration
            </h3>

            {/* 1. Select Node */}
            <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">Select Node to Configure</label>
                <select
                    className="w-full md:w-1/2 bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                    value={selectedNodeId}
                    onChange={e => setSelectedNodeId(e.target.value)}
                >
                    <option value="">-- Select a Node --</option>
                    {snmpNodes.map(n => (
                        <option key={n.id} value={n.id}>{n.name} ({n.ip})</option>
                    ))}
                </select>
                <p className="text-xs text-slate-500 mt-1">Only nodes with SNMP enabled are shown.</p>
            </div>

            {selectedNodeId && (
                <div className="animate-in fade-in duration-300 space-y-8">
                    <hr className="border-slate-700" />

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        {/* LEFT COL: Discovery & Interfaces */}
                        <div className="space-y-4">
                            <div className="flex items-center justify-between">
                                <h4 className="text-lg font-medium text-slate-200">1. Interfaces</h4>
                                <button
                                    onClick={handleDiscoverInterfaces}
                                    disabled={loadingInterfaces}
                                    className="text-primary hover:text-blue-300 text-sm flex items-center bg-blue-500/10 px-3 py-1.5 rounded-md transition-colors"
                                >
                                    {loadingInterfaces ? <Loader2 size={16} className="animate-spin mr-2" /> : <RefreshCw size={16} className="mr-2" />}
                                    Discover Interfaces
                                </button>
                            </div>

                            <div className="bg-slate-900/50 rounded-lg border border-slate-700/50 p-4 max-h-[400px] overflow-y-auto">
                                {interfaces.length > 0 ? (
                                    <div className="space-y-2">
                                        <div className="flex items-center pb-2 border-b border-slate-700/50">
                                            <input
                                                type="checkbox"
                                                checked={selectedInterfaces.size === interfaces.length}
                                                onChange={toggleAllInterfaces}
                                                className="rounded bg-slate-800 border-slate-600 text-primary mr-3"
                                            />
                                            <span className="text-sm font-medium text-slate-300">Select All ({interfaces.length})</span>
                                        </div>
                                        {interfaces.map(iface => (
                                            <label key={iface.index} className="flex items-center p-2 hover:bg-slate-800/50 rounded cursor-pointer transition-colors">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedInterfaces.has(iface.index)}
                                                    onChange={() => toggleSet(selectedInterfaces, setSelectedInterfaces, iface.index)}
                                                    className="rounded bg-slate-800 border-slate-600 text-primary mr-3"
                                                />
                                                <span className="text-sm text-slate-300 flex-1">{iface.name}</span>
                                                <span className="text-xs text-slate-500 font-mono">Idx: {iface.index}</span>
                                            </label>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-center py-8 text-slate-500">
                                        <AlertCircle className="mx-auto mb-2 opacity-50" />
                                        <p>No interfaces found yet.</p>
                                        <p className="text-xs">Click "Discover" to scan device.</p>
                                        {selectedInterfaces.size > 0 && (
                                            <p className="mt-4 text-orange-400 text-xs text-left px-4">
                                                Note: {selectedInterfaces.size} interfaces are currently configured but not shown because discovery hasn't been run. They will be preserved on save.
                                            </p>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* RIGHT COL: Metrics Selection */}
                        <div className="space-y-6">
                            {/* Interface Metrics */}
                            <div>
                                <h4 className="text-lg font-medium text-slate-200 mb-3">2. Interface Metrics</h4>
                                <p className="text-xs text-slate-400 mb-3">Applied to all selected interfaces.</p>
                                <div className="space-y-2">
                                    {ifDefs.map(def => (
                                        <label key={def.id} className="flex items-center p-3 bg-slate-800/30 border border-slate-700/50 rounded-lg cursor-pointer hover:bg-slate-800/50 transition-colors">
                                            <input
                                                type="checkbox"
                                                checked={selectedInterfaceMetrics.has(def.id)}
                                                onChange={() => toggleSet(selectedInterfaceMetrics, setSelectedInterfaceMetrics, def.id)}
                                                className="w-4 h-4 rounded bg-slate-800 border-slate-600 text-primary mr-3"
                                            />
                                            <div>
                                                <div className="text-sm font-medium text-slate-200">{def.name}</div>
                                                <div className="text-xs text-slate-500">OID: {def.oid_template}</div>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            {/* System Metrics */}
                            <div>
                                <h4 className="text-lg font-medium text-slate-200 mb-3">3. System Metrics</h4>
                                <div className="space-y-2">
                                    {sysDefs.map(def => (
                                        <label key={def.id} className="flex items-center p-3 bg-slate-800/30 border border-slate-700/50 rounded-lg cursor-pointer hover:bg-slate-800/50 transition-colors">
                                            <input
                                                type="checkbox"
                                                checked={selectedSystemMetrics.has(def.id)}
                                                onChange={() => toggleSet(selectedSystemMetrics, setSelectedSystemMetrics, def.id)}
                                                className="w-4 h-4 rounded bg-slate-800 border-slate-600 text-primary mr-3"
                                            />
                                            <div>
                                                <div className="text-sm font-medium text-slate-200">{def.name}</div>
                                                <div className="text-xs text-slate-500">Device: {def.device_type || 'Generic'}</div>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Action Bar */}
                    <div className="flex justify-end pt-6 border-t border-slate-700 sticky bottom-0 bg-surface pb-2">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="bg-primary hover:bg-blue-600 text-white px-6 py-2 rounded-md shadow-lg shadow-blue-900/20 flex items-center transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {saving ? <Loader2 size={18} className="animate-spin mr-2" /> : <Save size={18} className="mr-2" />}
                            Save Actions
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MetricsConfig;
