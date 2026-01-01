import React, { useState, useEffect } from 'react';
import api from '../api';
import { Activity, Server, Cpu, Thermometer, ArrowDown, ArrowUp, AlertCircle, Network } from 'lucide-react';

const MetricsDashboard = () => {
    const [nodes, setNodes] = useState([]);
    const [definitions, setDefinitions] = useState([]);
    const [nodeConfigs, setNodeConfigs] = useState({});

    // We need history to calculate rates. { metric_id: { value, timestamp } }
    // Actually, backend returns { value, timestamp } for current.
    // To calc rate, we need Previous value.
    // Let's store `metricHistory` ref: { metric_id: { value, timestamp } } (last known)
    // But `currentValues` from backend is just the LATEST.
    // Rate calculation usually requires persistence. 
    // If backend only gives "Current", we can only calc rate if WE poll frequently and diff against OUR last poll.
    // Better approach: Backend sends Rate? Or we derive it here. 
    // Let's derive it here client-side for now.

    const [currentValues, setCurrentValues] = useState({}); // metric_id -> {value, rate, timestamp}

    // Initial Load
    useEffect(() => {
        const loadMetadata = async () => {
            try {
                const defRes = await api.get('/metrics/definitions');
                setDefinitions(defRes.data);

                const groupRes = await api.get('/config/groups');
                const groups = groupRes.data;

                const nodeRes = await api.get('/config/nodes');
                const allNodes = nodeRes.data.filter(n => {
                    if (n.monitor_snmp === true) return true;
                    if (n.monitor_snmp === false) return false;
                    const group = groups.find(g => g.id === n.group_id);
                    return group ? group.monitor_snmp : false;
                });
                setNodes(allNodes);

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

    const formatBits = (bps) => {
        if (!bps && bps !== 0) return '-';
        if (bps >= 1000000000) return `${(bps / 1000000000).toFixed(2)} Gbps`;
        if (bps >= 1000000) return `${(bps / 1000000).toFixed(2)} Mbps`;
        if (bps >= 1000) return `${(bps / 1000).toFixed(2)} Kbps`;
        return `${Math.round(bps)} bps`;
    };

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

    const isTrafficMetric = (name) => {
        const n = name.toLowerCase();
        return n.includes('bytes') || n.includes('traffic');
    };

    return (
        <div className="space-y-6">
            <header className="flex items-center justify-between mb-8">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">SNMP Dashboard</h2>
                    <p className="text-slate-400">Real-time SNMP data</p>
                </div>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {nodes.map(node => {
                    const configs = nodeConfigs[node.id] || [];

                    const sysMetrics = configs.filter(c => {
                        const def = definitions.find(d => d.id === c.metric_definition_id);
                        return def && def.category !== 'interface';
                    });

                    // Organize Interface Metrics
                    const interfaces = {};
                    configs.forEach(c => {
                        const def = definitions.find(d => d.id === c.metric_definition_id);
                        if (def && def.category === 'interface') {
                            if (!interfaces[c.interface_index]) {
                                interfaces[c.interface_index] = {
                                    name: c.interface_name || `Idx ${c.interface_index}`,
                                    trafficIn: null,    // Metric Obj
                                    trafficOut: null,   // Metric Obj
                                    other: []
                                };
                            }
                            const ifObj = interfaces[c.interface_index];
                            const nameLower = def.name.toLowerCase();

                            if (nameLower.includes('in') && (nameLower.includes('bytes') || nameLower.includes('traffic'))) {
                                ifObj.trafficIn = { ...c, def };
                            } else if (nameLower.includes('out') && (nameLower.includes('bytes') || nameLower.includes('traffic'))) {
                                ifObj.trafficOut = { ...c, def };
                            } else {
                                ifObj.other.push({ ...c, def });
                            }
                        }
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
                                    <div className="grid grid-cols-2 gap-3 pb-2 border-b border-slate-800">
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
                                {Object.values(interfaces).length > 0 && (
                                    <div className="space-y-4">
                                        {Object.values(interfaces).map(iface => {
                                            // Get Rate from backend
                                            const rateIn = iface.trafficIn ? currentValues[iface.trafficIn.id]?.rate || 0 : 0;
                                            const rateOut = iface.trafficOut ? currentValues[iface.trafficOut.id]?.rate || 0 : 0;
                                            const rateTotal = rateIn + rateOut;

                                            // Calculate Total manually if needed, or if backend helps
                                            // But wait, Total is just In + Out sum. 
                                            // Backend doesn't have a "Total" metric unless we define one.
                                            // Summing rates client-side is fine.

                                            const hasTraffic = iface.trafficIn || iface.trafficOut;

                                            return (
                                                <div key={iface.name} className="bg-slate-900/30 rounded-lg border border-slate-700/30 overflow-hidden">
                                                    <div className="bg-slate-800/40 px-3 py-2 border-b border-slate-700/30 flex justify-between items-center">
                                                        <span className="font-medium text-slate-300 text-sm flex items-center">
                                                            <Network size={14} className="mr-2 text-blue-400" /> {iface.name}
                                                        </span>
                                                        {hasTraffic && <span className="text-xs font-mono text-blue-300">{formatBits(rateTotal)}</span>}
                                                    </div>

                                                    <div className="p-3 space-y-3">
                                                        {/* Traffic Section */}
                                                        {hasTraffic && (
                                                            <div className="grid grid-cols-2 gap-4">
                                                                <div className="space-y-1">
                                                                    <div className="text-[10px] uppercase text-slate-500 font-bold flex items-center">
                                                                        <ArrowDown size={10} className="mr-1" /> In
                                                                    </div>
                                                                    <div className="text-base font-mono text-white leading-none">{formatBits(rateIn)}</div>
                                                                    {/* <div className="text-[10px] text-slate-600 font-mono">Total: {formatValue(currentValues[iface.trafficIn?.id]?.value, 'counter', 'bytes')}</div> */}
                                                                </div>
                                                                <div className="space-y-1 text-right">
                                                                    <div className="text-[10px] uppercase text-slate-500 font-bold flex items-center justify-end">
                                                                        Out <ArrowUp size={10} className="ml-1" />
                                                                    </div>
                                                                    <div className="text-base font-mono text-white leading-none">{formatBits(rateOut)}</div>
                                                                </div>
                                                            </div>
                                                        )}

                                                        {/* Other Metrics (Errors, Status etc) */}
                                                        {iface.other.length > 0 && (
                                                            <div className={`grid grid-cols-2 gap-2 ${hasTraffic ? 'pt-2 border-t border-slate-700/30' : ''}`}>
                                                                {iface.other.map(m => {
                                                                    const val = currentValues[m.id]?.value;
                                                                    return (
                                                                        <div key={m.id} className="flex justify-between text-xs">
                                                                            <span className="text-slate-500 truncate">{m.def.name.replace('Interface ', '')}</span>
                                                                            <span className="text-slate-300 font-mono">{formatValue(val, m.def.metric_type, m.def.unit)}</span>
                                                                        </div>
                                                                    )
                                                                })}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}

                                {sysMetrics.length === 0 && Object.keys(interfaces).length === 0 && (
                                    <div className="text-center py-6 text-slate-500 text-sm">No metrics configured</div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
            {nodes.length === 0 && (
                <div className="text-center py-12 text-slate-500">No nodes found.</div>
            )}
        </div>
    );
};

export default MetricsDashboard;
