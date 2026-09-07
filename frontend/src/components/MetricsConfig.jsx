import React, { useState, useEffect, useMemo } from 'react';
import api from '../api';
import { RefreshCw, Check, Loader2, Network, Activity, ChevronRight, ChevronDown, Radar, EyeOff, Zap } from 'lucide-react';
import toast from 'react-hot-toast';

const NEVER_PROBED = 'never';

const MetricsConfig = ({ nodes, groups = [] }) => {
    const [selectedNodeId, setSelectedNodeId] = useState('');
    const [interfaces, setInterfaces] = useState([]);
    const [definitions, setDefinitions] = useState([]);
    const [capabilities, setCapabilities] = useState([]);

    // Configured metrics for the selected node
    const [localConfig, setLocalConfig] = useState([]);

    const [loading, setLoading] = useState(false);
    const [probing, setProbing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [expandedInterfaces, setExpandedInterfaces] = useState(new Set());
    const [showUnsupported, setShowUnsupported] = useState(false);

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
            setInterfaces([]); setLocalConfig([]); setCapabilities([]);
            return;
        }
        loadNodeData(selectedNodeId);
    }, [selectedNodeId]);

    const loadNodeData = async (nodeId) => {
        setLoading(true);
        try {
            const [ifRes, cfgRes, capRes] = await Promise.all([
                api.get(`/metrics/interfaces/${nodeId}`),
                api.get(`/metrics/nodes/${nodeId}`),
                api.get(`/metrics/capabilities/${nodeId}`),
            ]);
            setInterfaces(ifRes.data);
            setLocalConfig(cfgRes.data);
            setCapabilities(capRes.data);
        } catch (e) {
            console.error(e);
            toast.error("Failed to load node configuration");
        } finally {
            setLoading(false);
        }
    };

    // Ask the device what it supports, and refresh its interface list
    const handleProbe = async () => {
        if (!selectedNodeId) return;
        setProbing(true);
        try {
            const [capRes, ifRes] = await Promise.all([
                api.post(`/metrics/probe/${selectedNodeId}`),
                api.get(`/metrics/discover-interfaces/${selectedNodeId}`).catch(() => ({ data: interfaces })),
            ]);
            setCapabilities(capRes.data);
            setInterfaces(ifRes.data);
            const supported = capRes.data.filter(c => c.supported).length;
            toast.success(`Probe complete: ${supported} of ${capRes.data.length} candidates supported`);
        } catch (err) {
            console.error(err);
            const detail = err.response?.data?.detail;
            toast.error(detail || "Probe failed. Check the SNMP settings.");
        } finally {
            setProbing(false);
        }
    };

    // --- Capability lookup -------------------------------------------------

    const isProbed = capabilities.length > 0;

    const caps = useMemo(() => {
        // definition_id -> { scalarSupported, instances: [{index, label, supported}] }
        const map = {};
        capabilities.forEach(c => {
            if (!map[c.metric_definition_id]) map[c.metric_definition_id] = { scalarSupported: false, instances: [] };
            if (c.instance_index === null) {
                map[c.metric_definition_id].scalarSupported = c.supported;
            } else {
                map[c.metric_definition_id].instances.push({ index: c.instance_index, label: c.instance_label, supported: c.supported, sample: c.sample_value });
            }
        });
        return map;
    }, [capabilities]);

    const probedAt = useMemo(() => {
        const stamps = capabilities.map(c => c.probed_at).filter(Boolean);
        if (!stamps.length) return NEVER_PROBED;
        return new Date(Math.max(...stamps) * 1000).toLocaleString();
    }, [capabilities]);

    /** Supported when not probed (unknown = show everything), else per probe result. */
    const defSupported = (def) => {
        if (!isProbed) return true;
        const c = caps[def.id];
        if (!c) return false;
        return def.requires_index ? c.instances.some(i => i.supported) : c.scalarSupported;
    };

    const supportedInstances = (def) => (caps[def.id]?.instances || []).filter(i => i.supported);

    // --- Config mutations --------------------------------------------------

    const isMetricEnabled = (defId, ifaceIndex = null) =>
        localConfig.some(m => m.metric_definition_id === defId && m.interface_index === ifaceIndex && m.enabled);

    const configFor = (defId, ifaceIndex = null) =>
        localConfig.find(m => m.metric_definition_id === defId && m.interface_index === ifaceIndex);

    const handleUpdateMetric = async (defId, ifaceIndex = null, ifaceName = null, updates = {}) => {
        if (!selectedNodeId) return;
        const next = [...localConfig];
        const idx = next.findIndex(m => m.metric_definition_id === defId && m.interface_index === ifaceIndex);
        if (idx >= 0) {
            next[idx] = { ...next[idx], ...updates };
        } else {
            next.push({
                node_id: selectedNodeId, metric_definition_id: defId, interface_index: ifaceIndex,
                interface_name: ifaceName, collection_interval: 60, enabled: true, alert_enabled: true,
                alert_condition: 'gt', alert_min_samples: 2, warning_threshold: null, critical_threshold: null,
                ...updates
            });
        }
        saveConfig(next);
    };

    const handleToggleMetric = async (defId, ifaceIndex = null, ifaceName = null) => {
        if (!selectedNodeId) return;
        const next = [...localConfig];
        const idx = next.findIndex(m => m.metric_definition_id === defId && m.interface_index === ifaceIndex);
        if (idx >= 0) next.splice(idx, 1);
        else next.push({
            node_id: selectedNodeId, metric_definition_id: defId, interface_index: ifaceIndex,
            interface_name: ifaceName, collection_interval: 60, enabled: true, alert_enabled: true,
            alert_condition: 'gt', alert_min_samples: 2, warning_threshold: null, critical_threshold: null
        });
        saveConfig(next);
    };

    const saveConfig = async (next) => {
        setLocalConfig(next);
        setSaving(true);
        try {
            const payload = next.map(c => ({
                node_id: selectedNodeId,
                metric_definition_id: c.metric_definition_id,
                interface_index: c.interface_index,
                interface_name: c.interface_name,
                collection_interval: c.collection_interval || 60,
                enabled: true,
                alert_enabled: true,
                alert_condition: c.alert_condition || 'gt',
                alert_min_samples: c.alert_min_samples || 1,
                warning_threshold: c.warning_threshold,
                critical_threshold: c.critical_threshold
            }));
            await api.post(`/metrics/nodes/${selectedNodeId}`, payload);
        } catch (e) {
            console.error(e);
            toast.error("Failed to save configuration");
        } finally {
            setSaving(false);
        }
    };

    /** Enable every supported scalar system metric that is not configured yet. */
    const handleEnableSupported = () => {
        const next = [...localConfig];
        let added = 0;
        systemDefs.filter(d => defSupported(d) && !d.requires_index).forEach(def => {
            if (next.some(m => m.metric_definition_id === def.id && m.interface_index === null)) return;
            next.push({
                node_id: selectedNodeId, metric_definition_id: def.id, interface_index: null,
                interface_name: null, collection_interval: 60, enabled: true, alert_enabled: true,
                alert_condition: 'gt', alert_min_samples: 2, warning_threshold: null, critical_threshold: null
            });
            added++;
        });
        if (!added) { toast('All supported system metrics are already enabled'); return; }
        saveConfig(next);
        toast.success(`Enabled ${added} supported system metric${added === 1 ? '' : 's'}`);
    };

    // --- Derived lists -----------------------------------------------------

    const protocols = useMemo(() => {
        const node = nodes.find(n => n.id === selectedNodeId);
        if (!node) return { snmp: false, ping: false };
        const group = groups.find(g => g.id === node.group_id);
        return {
            snmp: node.monitor_snmp !== null ? node.monitor_snmp : (group?.monitor_snmp ?? false),
            ping: node.monitor_ping !== null ? node.monitor_ping : (group?.monitor_ping ?? true),
        };
    }, [selectedNodeId, nodes, groups]);

    const interfaceDefs = definitions.filter(d => d.category === 'interface');

    const systemDefs = definitions.filter(d => {
        if (d.category === 'interface') return false;
        const source = d.metric_source || 'snmp';
        if (source === 'snmp' && !protocols.snmp) return false;
        if (source === 'icmp' && !protocols.ping) return false;
        return true;
    });

    // ICMP metrics are computed locally, never probed: always treat as available
    const isIcmp = (def) => (def.metric_source || 'snmp') === 'icmp';
    const availableSystemDefs = systemDefs.filter(d => isIcmp(d) || defSupported(d));
    const hiddenSystemDefs = systemDefs.filter(d => !isIcmp(d) && !defSupported(d));
    const availableInterfaceDefs = interfaceDefs.filter(d => defSupported(d));

    const toggleExpand = (index) => {
        const next = new Set(expandedInterfaces);
        if (next.has(index)) next.delete(index); else next.add(index);
        setExpandedInterfaces(next);
    };

    // --- Threshold editor, shared by every metric row ---------------------

    const ThresholdRow = ({ def, index, label }) => {
        const config = configFor(def.id, index);
        if (!config) return null;
        return (
            <div className="flex flex-wrap items-end gap-3 mt-2">
                <div className="flex items-center gap-1">
                    <button
                        onClick={() => handleUpdateMetric(def.id, index, label, { alert_condition: 'lt' })}
                        className={`w-8 h-[26px] flex items-center justify-center text-xs rounded border transition-colors ${config.alert_condition === 'lt' ? 'bg-slate-700 border-slate-500 text-white font-bold' : 'bg-slate-900 border-slate-700 text-slate-500 hover:text-slate-300'}`}
                        title="Alert when the value is below the threshold"
                    >&lt;</button>
                    <button
                        onClick={() => handleUpdateMetric(def.id, index, label, { alert_condition: 'gt' })}
                        className={`w-8 h-[26px] flex items-center justify-center text-xs rounded border transition-colors ${(!config.alert_condition || config.alert_condition === 'gt') ? 'bg-slate-700 border-slate-500 text-white font-bold' : 'bg-slate-900 border-slate-700 text-slate-500 hover:text-slate-300'}`}
                        title="Alert when the value is above the threshold"
                    >&gt;</button>
                </div>
                <div>
                    <label className="text-[10px] text-slate-500 block font-medium">Warn</label>
                    <input type="number" placeholder="None"
                        value={config.warning_threshold ?? ''}
                        onChange={(e) => handleUpdateMetric(def.id, index, label, { warning_threshold: e.target.value === '' ? null : parseFloat(e.target.value) })}
                        className="w-20 h-[26px] bg-slate-900 border border-slate-700 rounded px-1.5 text-xs text-white focus:border-blue-500 outline-none" />
                </div>
                <div>
                    <label className="text-[10px] text-slate-500 block font-medium">Crit</label>
                    <input type="number" placeholder="None"
                        value={config.critical_threshold ?? ''}
                        onChange={(e) => handleUpdateMetric(def.id, index, label, { critical_threshold: e.target.value === '' ? null : parseFloat(e.target.value) })}
                        className="w-20 h-[26px] bg-slate-900 border border-slate-700 rounded px-1.5 text-xs text-white focus:border-red-500 outline-none" />
                </div>
                <div title="Consecutive samples past the threshold before an alert raises">
                    <label className="text-[10px] text-slate-500 block font-medium">Samples</label>
                    <input type="number" min="1" max="60"
                        value={config.alert_min_samples || 1}
                        onChange={(e) => handleUpdateMetric(def.id, index, label, { alert_min_samples: Math.max(1, parseInt(e.target.value) || 1) })}
                        className="w-14 h-[26px] bg-slate-900 border border-slate-700 rounded px-1.5 text-xs text-white focus:border-blue-500 outline-none" />
                </div>
            </div>
        );
    };

    const Checkbox = ({ checked, onChange, accent = 'bg-blue-500 border-blue-500' }) => (
        <div
            onClick={onChange}
            className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 cursor-pointer transition-colors ${checked ? accent : 'border-slate-600 hover:border-slate-500'}`}
        >
            {checked && <Check size={10} className="text-white" />}
        </div>
    );

    /** One system metric: a scalar checkbox, or one checkbox per discovered instance. */
    const SystemMetricRow = ({ def, dimmed }) => {
        const instances = supportedInstances(def);
        const manualIndex = def.requires_index && isProbed && instances.length === 0;

        return (
            <div className={`bg-slate-800/30 rounded-md p-3 border border-slate-700/30 ${dimmed ? 'opacity-60' : ''}`}>
                <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                        <div className="text-sm font-medium text-slate-200">{def.name}</div>
                        <div className="text-xs text-slate-500 font-mono truncate">{def.oid_template}</div>
                    </div>
                    <span className="text-[10px] uppercase text-slate-500 font-mono font-bold tracking-wider flex-shrink-0">{def.unit}</span>
                </div>

                {/* Scalar metric */}
                {!def.requires_index && (
                    <>
                        <label className="flex items-center gap-2 mt-2 cursor-pointer">
                            <Checkbox checked={isMetricEnabled(def.id)} onChange={() => handleToggleMetric(def.id)} accent="bg-purple-500 border-purple-500" />
                            <span className="text-xs text-slate-400">Collect this metric</span>
                            {caps[def.id]?.scalarSupported && caps[def.id]?.instances.length === 0 && capabilities.find(c => c.metric_definition_id === def.id)?.sample_value && (
                                <span className="text-xs text-slate-600 font-mono ml-auto">now: {capabilities.find(c => c.metric_definition_id === def.id).sample_value}</span>
                            )}
                        </label>
                        {isMetricEnabled(def.id) && <ThresholdRow def={def} index={null} label={null} />}
                    </>
                )}

                {/* Indexed metric with discovered instances */}
                {def.requires_index && instances.length > 0 && (
                    <div className="mt-2 space-y-2">
                        {instances.map(inst => {
                            const checked = isMetricEnabled(def.id, inst.index);
                            return (
                                <div key={inst.index} className="pl-1">
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <Checkbox checked={checked} onChange={() => handleToggleMetric(def.id, inst.index, inst.label || String(inst.index))} accent="bg-purple-500 border-purple-500" />
                                        <span className={`text-xs truncate ${checked ? 'text-white' : 'text-slate-400'}`}>
                                            {inst.label || `index ${inst.index}`}
                                        </span>
                                        <span className="text-[10px] text-slate-600 font-mono">#{inst.index}</span>
                                        {inst.sample && <span className="text-xs text-slate-600 font-mono ml-auto">now: {inst.sample}</span>}
                                    </label>
                                    {checked && <div className="pl-6"><ThresholdRow def={def} index={inst.index} label={inst.label || String(inst.index)} /></div>}
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Indexed metric with no instances found, or never probed: manual index */}
                {def.requires_index && instances.length === 0 && (
                    <div className="mt-2">
                        {(() => {
                            const entry = localConfig.find(m => m.metric_definition_id === def.id);
                            const checked = !!entry;
                            return (
                                <>
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <Checkbox checked={checked} onChange={() => handleToggleMetric(def.id, checked ? entry.interface_index : 1)} accent="bg-purple-500 border-purple-500" />
                                        <span className="text-xs text-slate-400">
                                            {manualIndex ? 'No instances found, set an index manually' : 'Collect, index set manually'}
                                        </span>
                                    </label>
                                    {checked && (
                                        <div className="flex items-center gap-2 mt-2 pl-6">
                                            <span className="text-[10px] text-slate-500">Index</span>
                                            <input type="number" value={entry.interface_index ?? 1}
                                                onChange={(e) => handleUpdateMetric(def.id, entry.interface_index, entry.interface_name, { interface_index: parseInt(e.target.value) || 1 })}
                                                className="w-16 h-[26px] bg-slate-900 border border-slate-700 rounded px-2 text-xs text-white outline-none focus:border-purple-500" />
                                            <span className="text-[10px] text-slate-500">Label</span>
                                            <input type="text" value={entry.interface_name || ''} placeholder="e.g. temp-CPU"
                                                onChange={(e) => handleUpdateMetric(def.id, entry.interface_index, e.target.value || null, { interface_name: e.target.value || null })}
                                                className="w-28 h-[26px] bg-slate-900 border border-slate-700 rounded px-2 text-xs text-white outline-none focus:border-purple-500" />
                                        </div>
                                    )}
                                    {checked && <div className="pl-6"><ThresholdRow def={def} index={entry.interface_index} label={entry.interface_name} /></div>}
                                </>
                            );
                        })()}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="bg-surface p-6 rounded-xl border border-slate-700 shadow-sm space-y-6">
            <h3 className="text-xl font-semibold text-slate-100 flex items-center justify-between">
                <span>Metrics Configuration</span>
                {saving && <span className="text-xs text-blue-400 flex items-center"><Loader2 size={12} className="animate-spin mr-1" /> Saving...</span>}
            </h3>

            {/* Node select and probe */}
            <div className="flex flex-col md:flex-row md:items-end gap-4">
                <div className="flex-1">
                    <label className="block text-sm font-medium text-slate-400 mb-2">Select Node</label>
                    <select
                        className="w-full md:w-96 bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white outline-none focus:border-primary"
                        value={selectedNodeId}
                        onChange={e => setSelectedNodeId(e.target.value)}
                    >
                        <option value="">-- Select a Node --</option>
                        {nodes.map(n => <option key={n.id} value={n.id}>{n.name} ({n.ip})</option>)}
                    </select>
                </div>

                {selectedNodeId && protocols.snmp && (
                    <div className="flex items-center gap-3">
                        <button
                            onClick={handleProbe}
                            disabled={probing}
                            className="flex items-center bg-primary hover:bg-blue-600 disabled:opacity-50 text-white px-4 py-2 rounded-md text-sm transition-colors"
                            title="Ask the device which metrics it supports and discover its instances"
                        >
                            {probing ? <Loader2 size={16} className="animate-spin mr-2" /> : <Radar size={16} className="mr-2" />}
                            {probing ? 'Probing...' : 'Probe device'}
                        </button>
                        <span className="text-xs text-slate-500">
                            {probedAt === NEVER_PROBED ? 'Never probed' : `Probed ${probedAt}`}
                        </span>
                    </div>
                )}

                {selectedNodeId && !protocols.snmp && (() => {
                    const orphaned = localConfig.filter(m => {
                        const def = definitions.find(d => d.id === m.metric_definition_id);
                        return def && (def.metric_source || 'snmp') === 'snmp';
                    }).length;
                    const warn = orphaned > 0;
                    return (
                        <div className={`flex items-center gap-2 text-xs rounded-md px-3 py-2 border ${warn ? 'bg-amber-500/10 border-amber-500/30 text-amber-200' : 'bg-slate-800/50 border-slate-700/50 text-slate-400'}`}>
                            <Radar size={14} className={`flex-shrink-0 ${warn ? 'text-amber-400' : 'text-slate-500'}`} />
                            <span>
                                {warn ? (
                                    <>
                                        <strong>{orphaned} SNMP metric{orphaned === 1 ? '' : 's'} configured, but SNMP is off for this node</strong>, so nothing is collected.
                                        Turn SNMP on under <strong>Nodes</strong>, then probe.
                                    </>
                                ) : (
                                    <>
                                        SNMP is off for this node, so there is nothing to probe.
                                        Turn it on under <strong className="text-slate-300">Nodes</strong> to collect interface and system metrics.
                                    </>
                                )}
                            </span>
                        </div>
                    );
                })()}
            </div>

            {selectedNodeId && !isProbed && protocols.snmp && (
                <div className="bg-blue-500/10 border border-blue-500/20 text-blue-200 px-4 py-3 rounded-lg text-sm flex items-start gap-3">
                    <Radar size={18} className="mt-0.5 flex-shrink-0 text-blue-400" />
                    <div>
                        <strong className="block">This device has not been probed.</strong>
                        Every metric is listed, including ones this model does not implement. Probing takes about a second and hides the metrics that return nothing, and it discovers sensors, disks and interfaces by name.
                    </div>
                </div>
            )}

            {loading && <div className="text-center py-8 text-slate-500">Loading...</div>}

            {selectedNodeId && !loading && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

                    {/* INTERFACES */}
                    {protocols.snmp && (
                        <div className="lg:col-span-2 space-y-4">
                            <div className="flex items-center justify-between">
                                <h4 className="text-lg font-medium text-slate-200 flex items-center gap-2">
                                    <Network size={20} className="text-blue-400" /> Interfaces
                                    {interfaces.length > 0 && <span className="text-xs text-slate-500 font-normal">{interfaces.length} found</span>}
                                </h4>
                                {availableInterfaceDefs.length < interfaceDefs.length && isProbed && (
                                    <span className="text-xs text-slate-500">
                                        {interfaceDefs.length - availableInterfaceDefs.length} metric{interfaceDefs.length - availableInterfaceDefs.length === 1 ? '' : 's'} not supported, hidden
                                    </span>
                                )}
                            </div>

                            <div className="bg-slate-900/50 rounded-lg border border-slate-700/50 overflow-hidden">
                                {interfaces.length > 0 ? (
                                    <table className="w-full text-left text-sm">
                                        <thead className="bg-slate-800/50 text-slate-400 border-b border-slate-700/50">
                                            <tr>
                                                <th className="px-4 py-3 w-10"></th>
                                                <th className="px-4 py-3">Index</th>
                                                <th className="px-4 py-3">Name</th>
                                                <th className="px-4 py-3">Status</th>
                                                <th className="px-4 py-3">Active</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-700/50">
                                            {interfaces.map(iface => {
                                                const isExpanded = expandedInterfaces.has(iface.index);
                                                const activeCount = localConfig.filter(m => {
                                                    if (m.interface_index !== iface.index) return false;
                                                    const def = definitions.find(d => d.id === m.metric_definition_id);
                                                    return def && def.category === 'interface';
                                                }).length;

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
                                                            <td className="px-4 py-3 font-medium text-slate-200 max-w-xs truncate" title={iface.name}>
                                                                {iface.name} <span className="text-slate-500 font-normal ml-2">{iface.alias}</span>
                                                            </td>
                                                            <td className="px-4 py-3">
                                                                {String(iface.admin_status) === '1' || String(iface.admin_status) === 'up'
                                                                    ? <span className="text-xs text-green-400">UP</span>
                                                                    : <span className="text-xs text-red-500">DOWN</span>}
                                                            </td>
                                                            <td className="px-4 py-3">
                                                                {activeCount > 0
                                                                    ? <span className="bg-blue-500 text-white text-xs px-2 py-0.5 rounded-full">{activeCount}</span>
                                                                    : <span className="text-slate-600">-</span>}
                                                            </td>
                                                        </tr>

                                                        {isExpanded && (
                                                            <tr className="bg-slate-900/80">
                                                                <td colSpan={5} className="px-4 py-4 border-l-2 border-blue-500/50">
                                                                    <div className="pl-4 grid grid-cols-1 md:grid-cols-2 gap-3">
                                                                        {availableInterfaceDefs.map(def => {
                                                                            const checked = isMetricEnabled(def.id, iface.index);
                                                                            return (
                                                                                <div key={def.id} className={`p-2 rounded border transition-colors ${checked ? 'bg-slate-800/80 border-slate-600' : 'border-transparent hover:bg-slate-800/30'}`}>
                                                                                    <label className="flex items-center gap-2 cursor-pointer">
                                                                                        <Checkbox checked={checked} onChange={() => handleToggleMetric(def.id, iface.index, iface.name)} />
                                                                                        <span className={`text-sm ${checked ? 'text-white' : 'text-slate-400'}`}>
                                                                                            {def.name.replace('Interface ', '')}
                                                                                        </span>
                                                                                        <span className="text-[10px] uppercase text-slate-500 font-mono ml-auto">{def.unit}</span>
                                                                                    </label>
                                                                                    {checked && <ThresholdRow def={def} index={iface.index} label={iface.name} />}
                                                                                </div>
                                                                            );
                                                                        })}
                                                                        {availableInterfaceDefs.length === 0 && (
                                                                            <div className="text-slate-500 text-sm">This device supports no interface metrics.</div>
                                                                        )}
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
                                    <div className="text-center py-12 text-slate-500">
                                        No interfaces known. Use <strong>Probe device</strong> to discover them.
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* SYSTEM METRICS */}
                    <div className={protocols.snmp ? '' : 'lg:col-span-3'}>
                        <div className="flex items-center justify-between mb-3">
                            <h4 className="text-lg font-medium text-slate-200 flex items-center gap-2">
                                <Activity size={20} className="text-purple-400" /> System Metrics
                            </h4>
                            {isProbed && availableSystemDefs.length > 0 && (
                                <button
                                    onClick={handleEnableSupported}
                                    className="text-xs text-primary hover:text-blue-300 flex items-center gap-1 bg-blue-500/10 px-2 py-1 rounded"
                                    title="Enable every supported metric that has no index"
                                >
                                    <Zap size={12} /> Enable all
                                </button>
                            )}
                        </div>

                        <div className="space-y-2">
                            {availableSystemDefs.map(def => <SystemMetricRow key={def.id} def={def} />)}
                            {availableSystemDefs.length === 0 && (
                                <div className="text-center py-8 text-slate-500 text-sm bg-slate-900/30 rounded-lg border border-slate-700/30">
                                    {protocols.snmp
                                        ? 'No supported system metrics on this device.'
                                        : 'Only ICMP metrics are available while SNMP is off, and none are defined.'}
                                </div>
                            )}
                        </div>

                        {/* Unsupported, collapsed */}
                        {hiddenSystemDefs.length > 0 && (
                            <div className="mt-4">
                                <button
                                    onClick={() => setShowUnsupported(!showUnsupported)}
                                    className="w-full flex items-center justify-between px-3 py-2 text-xs text-slate-400 hover:text-slate-200 bg-slate-900/40 rounded-lg border border-slate-700/30 transition-colors"
                                >
                                    <span className="flex items-center gap-2">
                                        <EyeOff size={14} /> Not supported by this device ({hiddenSystemDefs.length})
                                    </span>
                                    {showUnsupported ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                </button>
                                {showUnsupported && (
                                    <div className="space-y-2 mt-2">
                                        <p className="text-xs text-slate-500 px-1">
                                            These returned no value when probed. You can still enable one, for example if the device gained the OID after a firmware update.
                                        </p>
                                        {hiddenSystemDefs.map(def => <SystemMetricRow key={def.id} def={def} dimmed />)}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default MetricsConfig;
