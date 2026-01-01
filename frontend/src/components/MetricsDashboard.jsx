import React, { useState, useEffect } from 'react';
import api from '../api';
import { Activity, Server, Cpu, Thermometer, ArrowDown, ArrowUp, AlertCircle } from 'lucide-react';

const MetricsDashboard = () => {
    const [nodes, setNodes] = useState([]);
    const [definitions, setDefinitions] = useState([]);
    const [nodeConfigs, setNodeConfigs] = useState({}); // node_id -> [NodeMetric]
    const [currentValues, setCurrentValues] = useState({}); // metric_id -> {value, timestamp}

    // Initial Load
    useEffect(() => {
        const loadMetadata = async () => {
            try {
                // Load Definitions
                const defRes = await api.get('/metrics/definitions');
                setDefinitions(defRes.data);

                // Load Nodes
                const nodeRes = await api.get('/config/nodes');
                const allNodes = nodeRes.data.filter(n => n.monitor_snmp || n.group_monitor_snmp !== false);
                setNodes(allNodes);

                // Load Configs for all relevant nodes
                const configs = {};
                await Promise.all(allNodes.map(async (n) => {
                    try {
                        const res = await api.get(`/metrics/nodes/${n.id}`);
                        configs[n.id] = res.data;
                    } catch (e) {
                        console.error(`Failed to load config for ${n.name}`, e);
                    }
                }));
                setNodeConfigs(configs);

            } catch (e) {
                console.error("Failed to load metadata", e);
            }
        };

        loadMetadata();
    }, []);

    // Data Polling
    useEffect(() => {
        const fetchMetrics = async () => {
            try {
                const res = await api.get('/metrics/current');
                setCurrentValues(res.data);
            } catch (e) {
                console.error("Failed to fetch metrics", e);
            }
        };

        fetchMetrics();
        const interval = setInterval(fetchMetrics, 5000);
        return () => clearInterval(interval);
    }, []);

    const formatValue = (val, type, unit) => {
        if (val === undefined || val === null) return '-';
        if (unit === 'bytes') {
            const bytes = parseInt(val);
            if (isNaN(bytes)) return val;
            if (bytes > 1000000000) return `${(bytes / 1000000000).toFixed(2)} GB`;
            if (bytes > 1000000) return `${(bytes / 1000000).toFixed(2)} MB`;
            if (bytes > 1000) return `${(bytes / 1000).toFixed(2)} KB`;
            return `${bytes} B`;
        }
        if (unit === 'percent') return `${val}%`;
        if (unit === 'celsius') return `${val}°C`;
        return val;
    };

    // Group metrics by node for display
    return (
        <div className="space-y-6">
            <header className="flex items-center justify-between mb-8">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">Metrics Dashboard</h2>
                    <p className="text-slate-400">Real-time SNMP data</p>
                </div>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {nodes.map(node => {
                    const configs = nodeConfigs[node.id] || [];
                    if (configs.length === 0) return null;

                    // Group metrics 
                    const sysMetrics = configs.filter(c => {
                        const def = definitions.find(d => d.id === c.metric_definition_id);
                        return def && def.category !== 'interface';
                    });

                    const ifMetrics = configs.filter(c => {
                        const def = definitions.find(d => d.id === c.metric_definition_id);
                        return def && def.category === 'interface';
                    });

                    // Group interfaces
                    const interfaces = {}; // index -> {name, metrics: []}
                    ifMetrics.forEach(m => {
                        const def = definitions.find(d => d.id === m.metric_definition_id);
                        if (!interfaces[m.interface_index]) {
                            interfaces[m.interface_index] = {
                                name: m.interface_name || `Index ${m.interface_index}`,
                                metrics: []
                            };
                        }
                        interfaces[m.interface_index].metrics.push({ ...m, def });
                    });

                    return (
                        <div key={node.id} className="bg-surface rounded-xl border border-slate-700 shadow-sm overflow-hidden flex flex-col">
                            <div className="p-4 bg-slate-800/50 border-b border-slate-700 flex justify-between items-center">
                                <h3 className="font-semibold text-slate-100 flex items-center">
                                    <Server size={18} className="mr-2 text-primary" />
                                    {node.name}
                                </h3>
                                <div className="text-xs text-slate-500 font-mono">{node.ip}</div>
                            </div>

                            <div className="p-4 space-y-4 flex-1">
                                {/* System Metrics */}
                                {sysMetrics.length > 0 && (
                                    <div className="grid grid-cols-2 gap-3">
                                        {sysMetrics.map(m => {
                                            const def = definitions.find(d => d.id === m.metric_definition_id);
                                            const data = currentValues[m.id];
                                            const val = data ? data.value : null;

                                            let Icon = Activity;
                                            if (def.name.toLowerCase().includes('cpu')) Icon = Cpu;
                                            if (def.name.toLowerCase().includes('temp')) Icon = Thermometer;

                                            return (
                                                <div key={m.id} className="bg-slate-900/50 p-3 rounded-lg border border-slate-700/50">
                                                    <div className="flex items-center text-slate-400 text-xs mb-1">
                                                        <Icon size={12} className="mr-1" /> {def.name}
                                                    </div>
                                                    <div className="text-xl font-mono text-white">
                                                        {formatValue(val, def.metric_type, def.unit)}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}

                                {/* Interfaces */}
                                {Object.keys(interfaces).length > 0 && (
                                    <div className="space-y-3">
                                        <h4 className="text-xs uppercase font-bold text-slate-500 tracking-wider">Interfaces</h4>
                                        <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2">
                                            {Object.values(interfaces).map(iface => (
                                                <div key={iface.name} className="bg-slate-900/30 p-3 rounded-lg border border-slate-700/30 text-sm">
                                                    <div className="font-medium text-slate-300 mb-2 border-b border-slate-700/30 pb-1">
                                                        {iface.name}
                                                    </div>
                                                    <div className="grid grid-cols-2 gap-y-2 gap-x-4">
                                                        {iface.metrics.map(im => {
                                                            const data = currentValues[im.id];
                                                            const val = data ? data.value : null;

                                                            return (
                                                                <div key={im.id} className="flex justify-between items-center">
                                                                    <span className="text-slate-500 text-xs truncate max-w-[60%]">{im.def.name.replace('Interface ', '')}</span>
                                                                    <span className="text-slate-200 font-mono text-xs">
                                                                        {formatValue(val, im.def.metric_type, im.def.unit)}
                                                                    </span>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {sysMetrics.length === 0 && Object.keys(interfaces).length === 0 && (
                                    <div className="text-center py-8 text-slate-500 text-sm">
                                        <AlertCircle className="mx-auto mb-2 opacity-50" size={24} />
                                        No metrics configured.
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
            {nodes.length === 0 && (
                <div className="text-center py-12 text-slate-500">
                    <p>No SNMP-enabled nodes found.</p>
                </div>
            )}
        </div>
    );
};

export default MetricsDashboard;
