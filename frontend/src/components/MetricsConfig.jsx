import React, { useState, useEffect } from 'react';
import api from '../api';
import { Save, RefreshCw, Check, AlertCircle, Loader2, Network, Activity, ChevronRight, ChevronDown } from 'lucide-react';
import toast from 'react-hot-toast';

const MetricsConfig = ({ nodes, groups = [] }) => {
    const [selectedNodeId, setSelectedNodeId] = useState('');
    const [interfaces, setInterfaces] = useState([]);
    const [definitions, setDefinitions] = useState([]);

    // Unified configuration state: List of metric objects { metric_definition_id, interface_index, ... }
    const [localConfig, setLocalConfig] = useState([]);

    const [loadingInterfaces, setLoadingInterfaces] = useState(false);
    const [scanning, setScanning] = useState(false);
    const [saving, setSaving] = useState(false);
    const [expandedInterfaces, setExpandedInterfaces] = useState(new Set());

    const snmpNodes = nodes.filter(n => {
        if (n.monitor_snmp === true) return true;
        if (n.monitor_snmp === false) return false;
        const group = groups.find(g => g.id === n.group_id);
        return group ? group.monitor_snmp : false;
    });

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

    useEffect(() => {
        if (!selectedNodeId) {
            setInterfaces([]);
            setLocalConfig([]);
            return;
        }
        loadNodeData(selectedNodeId);
    }, [selectedNodeId]);

    const loadNodeData = async (nodeId) => {
        setLoadingInterfaces(true);
        try {
            // Load Interfaces
            const ifRes = await api.get(`/metrics/interfaces/${nodeId}`);
            setInterfaces(ifRes.data);

            // Load Configured Metrics
            const configRes = await api.get(`/metrics/nodes/${nodeId}`);
            setLocalConfig(configRes.data);

        } catch (e) {
            console.error(e);
            toast.error("Failed to load node configuration");
        } finally {
            setLoadingInterfaces(false);
        }
    };

    const handleScanInterfaces = async () => {
        if (!selectedNodeId) return;
        setScanning(true);
        try {
            const res = await api.get(`/metrics/discover-interfaces/${selectedNodeId}`);
            setInterfaces(res.data);
            toast.success(`Scan complete. Found ${res.data.length} interfaces.`);
        } catch (err) {
            console.error(err);
            toast.error("Scan failed. Check SNMP settings.");
        } finally {
            setScanning(false);
        }
    };

    const toggleExpand = (index) => {
        const newSet = new Set(expandedInterfaces);
        if (newSet.has(index)) newSet.delete(index);
        else newSet.add(index);
        setExpandedInterfaces(newSet);
    };

    const isMetricEnabled = (defId, ifaceIndex = null) => {
        return localConfig.some(m =>
            m.metric_definition_id === defId &&
            m.interface_index === ifaceIndex &&
            m.enabled
        );
    };

    const handleToggleMetric = async (defId, ifaceIndex = null, ifaceName = null) => {
        if (!selectedNodeId) return;

        // Clone current config
        let newConfig = [...localConfig];
        const existingIdx = newConfig.findIndex(m =>
            m.metric_definition_id === defId &&
            m.interface_index === ifaceIndex
        );

        if (existingIdx >= 0) {
            // Remove (Toggle Off)
            newConfig.splice(existingIdx, 1);
        } else {
            // Add (Toggle On)
            newConfig.push({
                node_id: selectedNodeId,
                metric_definition_id: defId,
                interface_index: ifaceIndex,
                interface_name: ifaceName,
                collection_interval: 60,
                enabled: true
            });
        }

        // Optimistic Update
        setLocalConfig(newConfig);

        // Save
        setSaving(true);
        try {
            // Filter out internal fields before sending 'Create' payloads if needed?
            // The API expects NodeMetricCreate schemas.
            // Our local config has DB fields (id, created_at) which API ignores or handles.
            // We should map to clean objects.
            const payload = newConfig.map(c => ({
                node_id: selectedNodeId,
                metric_definition_id: c.metric_definition_id,
                interface_index: c.interface_index,
                interface_name: c.interface_name,
                collection_interval: c.collection_interval || 60,
                enabled: true
            }));

            await api.post(`/metrics/nodes/${selectedNodeId}`, payload);
            // Don't toast on every click, too noisy. Maybe a small indicator?
        } catch (e) {
            console.error(e);
            toast.error("Failed to save configuration");
            // Revert on error? For now rely on reload or retry.
        } finally {
            setSaving(false);
        }
    };

    // Derived Lists
    const interfaceDefs = definitions.filter(d => d.category === 'interface');
    const systemDefs = definitions.filter(d => d.category !== 'interface');

    return (
        <div className="bg-surface p-6 rounded-xl border border-slate-700 shadow-sm space-y-6">
            <h3 className="text-xl font-semibold text-slate-100 flex items-center justify-between">
                <span>SNMP Metrics Configuration</span>
                {saving && <span className="text-xs text-blue-400 flex items-center"><Loader2 size={12} className="animate-spin mr-1" /> Saving...</span>}
            </h3>

            {/* Node Select */}
            <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">Select Node</label>
                <select
                    className="w-full md:w-1/2 bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white outline-none focus:border-primary"
                    value={selectedNodeId}
                    onChange={e => setSelectedNodeId(e.target.value)}
                >
                    <option value="">-- Select a Node --</option>
                    {snmpNodes.map(n => (
                        <option key={n.id} value={n.id}>{n.name} ({n.ip})</option>
                    ))}
                </select>
            </div>

            {selectedNodeId && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 animate-in fade-in">

                    {/* INTERFACES COLUMN */}
                    <div className="lg:col-span-2 space-y-4">
                        <div className="flex items-center justify-between">
                            <h4 className="text-lg font-medium text-slate-200 flex items-center gap-2">
                                <Network size={20} className="text-blue-400" /> Interfaces
                            </h4>
                            <button
                                onClick={handleScanInterfaces}
                                disabled={scanning}
                                className="text-primary hover:text-blue-300 text-sm flex items-center bg-blue-500/10 px-3 py-1.5 rounded-md transition-colors"
                            >
                                {scanning ? <Loader2 size={16} className="animate-spin mr-2" /> : <RefreshCw size={16} className="mr-2" />}
                                {scanning ? "Scanning..." : "Scan Interfaces"}
                            </button>
                        </div>

                        <div className="bg-slate-900/50 rounded-lg border border-slate-700/50 overflow-hidden">
                            {loadingInterfaces ? (
                                <div className="p-8 text-center text-slate-500">Loading...</div>
                            ) : interfaces.length > 0 ? (
                                <table className="w-full text-left text-sm">
                                    <thead className="bg-slate-800/50 text-slate-400 border-b border-slate-700/50">
                                        <tr>
                                            <th className="px-4 py-3 w-10"></th>
                                            <th className="px-4 py-3">Index</th>
                                            <th className="px-4 py-3">Name</th>
                                            <th className="px-4 py-3">Status</th>
                                            <th className="px-4 py-3">Active Metrics</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-700/50">
                                        {interfaces.map(iface => {
                                            const isExpanded = expandedInterfaces.has(iface.index);
                                            // Count active metrics for summary (only interface category)
                                            const activeCount = localConfig.filter(m => {
                                                if (m.interface_index !== iface.index) return false;
                                                const def = definitions.find(d => d.id === m.metric_definition_id);
                                                return def && def.category === 'interface';
                                            }).length;

                                            // Auto-expand if active metrics exist (optional UX choice, keeping manual for now or auto on load?)
                                            // Let's keep manual expansion, but highlight row if active.

                                            return (
                                                <React.Fragment key={iface.index}>
                                                    <tr
                                                        className={`hover:bg-slate-800/30 transition-colors cursor-pointer ${activeCount > 0 ? 'bg-blue-900/10' : ''}`}
                                                        onClick={() => toggleExpand(iface.index)}
                                                    >
                                                        <td className="px-4 py-3 text-slate-500">
                                                            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                                                        </td>
                                                        <td className="px-4 py-3 font-mono text-slate-500">{iface.index}</td>
                                                        <td className="px-4 py-3 font-medium text-slate-200">
                                                            {iface.name} <span className="text-slate-500 font-normal ml-2">{iface.alias}</span>
                                                        </td>
                                                        <td className="px-4 py-3">
                                                            {/* Status Badges */}
                                                            {String(iface.admin_status) === '1' || String(iface.admin_status) === 'up' ?
                                                                <span className="text-xs text-green-400">UP</span> :
                                                                <span className="text-xs text-red-500">DOWN</span>
                                                            }
                                                        </td>
                                                        <td className="px-4 py-3">
                                                            {activeCount > 0 ? (
                                                                <span className="bg-blue-500 text-white text-xs px-2 py-0.5 rounded-full">{activeCount}</span>
                                                            ) : (
                                                                <span className="text-slate-600">-</span>
                                                            )}
                                                        </td>
                                                    </tr>

                                                    {isExpanded && (
                                                        <tr className="bg-slate-900/80">
                                                            <td colSpan={5} className="px-4 py-4 border-l-2 border-blue-500/50">
                                                                <div className="pl-4">
                                                                    <h5 className="text-xs uppercase text-slate-500 font-bold mb-3 tracking-wider">Available Metrics</h5>
                                                                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                                                        {interfaceDefs.map(def => {
                                                                            const isChecked = isMetricEnabled(def.id, iface.index);
                                                                            return (
                                                                                <label key={def.id} className="flex items-center space-x-2 cursor-pointer group">
                                                                                    <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${isChecked ? 'bg-blue-500 border-blue-500' : 'border-slate-600 group-hover:border-slate-500'}`}>
                                                                                        {isChecked && <Check size={10} className="text-white" />}
                                                                                    </div>
                                                                                    <input
                                                                                        type="checkbox"
                                                                                        className="hidden"
                                                                                        checked={isChecked}
                                                                                        onChange={() => handleToggleMetric(def.id, iface.index, iface.name)}
                                                                                    />
                                                                                    <span className={`text-sm ${isChecked ? 'text-white' : 'text-slate-400 group-hover:text-slate-300'}`}>
                                                                                        {def.name.replace('Interface ', '')
                                                                                            .replace('Bytes In', 'Traffic In (Legacy)')
                                                                                            .replace('Bytes Out', 'Traffic Out (Legacy)')}
                                                                                    </span>
                                                                                </label>
                                                                            );
                                                                        })}
                                                                    </div>
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    )}
                                                </React.Fragment>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            ) : (
                                <div className="text-center py-12 text-slate-500">No interfaces found. Scan to discover.</div>
                            )}
                        </div>
                    </div>

                    {/* SYSTEM METRICS COLUMN */}
                    <div>
                        <h4 className="text-lg font-medium text-slate-200 mb-3 flex items-center gap-2">
                            <Activity size={20} className="text-purple-400" /> System Metrics
                        </h4>
                        <div className="bg-slate-900/30 rounded-lg p-1 border border-slate-700/30 space-y-0.5">
                            {systemDefs.map(def => {
                                // Find specific config entry
                                const configEntry = localConfig.find(m => m.metric_definition_id === def.id);
                                const isChecked = !!configEntry;
                                const currentIndex = configEntry ? (configEntry.interface_index ?? 1) : 1;

                                return (
                                    <div key={def.id} className="flex items-center justify-between p-3 hover:bg-slate-800/50 rounded-md transition-colors group">
                                        <label className="flex items-center cursor-pointer flex-1">
                                            <div className={`w-4 h-4 rounded border flex items-center justify-center mr-3 transition-colors ${isChecked ? 'bg-purple-500 border-purple-500' : 'border-slate-600'}`}>
                                                {isChecked && <Check size={10} className="text-white" />}
                                            </div>
                                            <input
                                                type="checkbox"
                                                className="hidden"
                                                checked={isChecked}
                                                // If toggling on, check if index is required. 
                                                // If toggling off, pass the current index to ensure removal match.
                                                onChange={() => {
                                                    if (isChecked) {
                                                        // Toggle Off: remove by passing current index (could be null or a number)
                                                        handleToggleMetric(def.id, configEntry.interface_index);
                                                    } else {
                                                        // Toggle On: default to 1 if index required, else null
                                                        const idx = def.requires_index ? 1 : null;
                                                        handleToggleMetric(def.id, idx);
                                                    }
                                                }}
                                            />
                                            <div>
                                                <div className={`text-sm font-medium ${isChecked ? 'text-white' : 'text-slate-300'}`}>{def.name}</div>
                                                <div className="text-xs text-slate-500">{def.oid_template}</div>
                                            </div>
                                        </label>

                                        {def.requires_index && isChecked && (
                                            <div className="ml-4 flex items-center space-x-2">
                                                <span className="text-xs text-slate-500">Idx:</span>
                                                <input
                                                    type="number"
                                                    className="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:border-purple-500 outline-none"
                                                    value={currentIndex}
                                                    onChange={(e) => {
                                                        const val = parseInt(e.target.value);
                                                        // Update existing entry with new index
                                                        const newConfig = localConfig.map(c =>
                                                            c.metric_definition_id === def.id ? { ...c, interface_index: val } : c
                                                        );
                                                        setLocalConfig(newConfig);
                                                    }}
                                                    onClick={(e) => e.stopPropagation()}
                                                />
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                </div>
            )}
        </div>
    );
};

export default MetricsConfig;
