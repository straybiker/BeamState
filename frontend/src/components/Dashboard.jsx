import React, { useEffect, useState } from 'react';
import api from '../api';
import { Wifi, WifiOff, Clock, Activity, PauseCircle } from 'lucide-react';
import toast from 'react-hot-toast';

const Dashboard = () => {
    const [statusData, setStatusData] = useState([]);
    const [groups, setGroups] = useState([]); // Store groups configuration
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        try {
            // Fetch groups config to ensure we show all groups (even empty ones)
            const groupsRes = await api.get('/config/groups');
            setGroups(groupsRes.data);

            // Fetch pinger status which includes latest results
            const statusRes = await api.get('/status');
            if (statusRes.data && statusRes.data.latest_results) {
                setStatusData(statusRes.data.latest_results);
            }
        } catch (error) {
            console.error("Failed to fetch data:", error);
            toast.error('Failed to load dashboard data');
        } finally {
            setLoading(false);
        }
    };

    const fetchStatusOnly = async () => {
        try {
            const statusRes = await api.get('/status');
            if (statusRes.data && statusRes.data.latest_results) {
                setStatusData(statusRes.data.latest_results);
            }
        } catch (error) {
            console.error("Poll error:", error);
            // Silent fail for polling - don't spam user with toasts
        }
    };

    useEffect(() => {
        fetchData();
        // Poll status periodically
        const interval = setInterval(() => {
            fetchStatusOnly();
        }, 5000);

        // Poll configuration periodically to catch added/removed nodes
        const configInterval = setInterval(() => {
            api.get('/config/groups').then(res => setGroups(res.data)).catch(e => console.error(e));
        }, 5000);

        return () => {
            clearInterval(interval);
            clearInterval(configInterval);
        };
    }, []);

    // Group pinger results by group_name for easy lookup
    const resultsByGroup = statusData.reduce((acc, item) => {
        if (!acc[item.group_name]) acc[item.group_name] = [];
        acc[item.group_name].push(item);
        return acc;
    }, {});

    if (loading && groups.length === 0) return <div className="text-center p-10 text-slate-400">Loading Dashboard...</div>;

    return (
        <div className="space-y-8">
            <header className="mb-6 flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">Monitoring Dashboard</h2>
                    <p className="text-slate-400">Real-time status of monitored devices</p>
                </div>
                <img
                    src="/logo_transparant.png"
                    alt="BeamState Logo"
                    className="h-16 object-contain"
                />
            </header>

            {/* Summary Stats */}
            {(() => {
                let stats = { up: 0, down: 0, warning: 0, paused: 0, total: 0 };
                groups.forEach(group => {
                    const groupResults = resultsByGroup[group.name] || [];
                    const resultsMap = new Map(groupResults.map(r => [r.node_id, r]));
                    const nodes = group.nodes || [];

                    nodes.forEach(node => {
                        stats.total++;
                        // If group is paused, node is effectively paused unless status says otherwise? 
                        // Actually backend status handles group pause. 
                        // But if no status yet, and group paused, it's paused.

                        const statusNode = resultsMap.get(node.id);
                        let status = 'WAITING';

                        if (statusNode) {
                            status = statusNode.status;
                        } else if (group.enabled === false) {
                            status = 'PAUSED';
                        }

                        if (status === 'UP') stats.up++;
                        else if (status === 'DOWN') stats.down++;
                        else if (status === 'PENDING') stats.warning++;
                        else if (status === 'PAUSED') stats.paused++;
                        // WAITING counts towards total but not specific buckets here, or maybe warning?
                        // Let's treat WAITING as warning/pending for now or just ignore
                    });
                });

                return (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                        <div className="bg-slate-800/50 p-3 rounded-xl border border-slate-700/50 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-green-500/10">
                                    <Wifi size={20} className="text-green-400" />
                                </div>
                                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Up</div>
                            </div>
                            <div className="text-2xl font-bold text-green-400 leading-none">{stats.up}</div>
                        </div>
                        <div className="bg-slate-800/50 p-3 rounded-xl border border-slate-700/50 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-red-500/10">
                                    <WifiOff size={20} className="text-red-400" />
                                </div>
                                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Down</div>
                            </div>
                            <div className="text-2xl font-bold text-red-400 leading-none">{stats.down}</div>
                        </div>
                        <div className="bg-slate-800/50 p-3 rounded-xl border border-slate-700/50 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-orange-500/10">
                                    <Clock size={20} className="text-orange-400" />
                                </div>
                                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Warning</div>
                            </div>
                            <div className="text-2xl font-bold text-orange-400 leading-none">{stats.warning}</div>
                        </div>
                        <div className="bg-slate-800/50 p-3 rounded-xl border border-slate-700/50 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-slate-500/10">
                                    <PauseCircle size={20} className="text-slate-400" />
                                </div>
                                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Paused</div>
                            </div>
                            <div className="text-2xl font-bold text-slate-400 leading-none">{stats.paused}</div>
                        </div>
                    </div>
                );
            })()}

            {groups.length === 0 && (
                <div className="bg-surface p-6 rounded-lg text-center text-slate-400 border border-slate-700">
                    No groups configured. Go to Configuration to add groups.
                </div>
            )}

            {groups.map((group) => {
                // Get results for this group's name
                const groupResults = resultsByGroup[group.name] || [];
                const resultsMap = new Map(groupResults.map(r => [r.node_id, r]));

                // Use configured nodes from the group definition
                const nodesToRender = group.nodes || [];

                // If the group is empty (no configured nodes)
                if (nodesToRender.length === 0) {
                    return (
                        <div key={group.id} className={`rounded-xl p-6 border shadow-sm transition-colors ${group.enabled === false ? 'bg-slate-900 border-slate-800 opacity-60' : 'bg-surface border-slate-700'}`}>
                            <h3 className={`text-xl font-semibold mb-4 border-b pb-2 flex justify-between items-center ${group.enabled === false ? 'text-slate-500 border-slate-800' : 'text-primary border-slate-700'}`}>
                                <div className="flex items-center">
                                    {group.enabled === false && <PauseCircle size={20} className="mr-2" />}
                                    <span>{group.enabled === false ? `${group.name} - PAUSED` : group.name}</span>
                                </div>
                                <span className="text-xs text-slate-500 font-normal">0 nodes</span>
                            </h3>

                            <div className="text-center py-8 text-slate-500 bg-slate-800/20 rounded-lg border border-dashed border-slate-700">
                                This group is empty
                            </div>
                        </div>
                    );
                }

                return (
                    <div key={group.id} className={`rounded-xl p-6 border shadow-sm transition-colors ${group.enabled === false ? 'bg-slate-900 border-slate-800 opacity-60' : 'bg-surface border-slate-700'}`}>
                        <h3 className={`text-xl font-semibold mb-4 border-b pb-2 flex justify-between items-center ${group.enabled === false ? 'text-slate-500 border-slate-800' : 'text-primary border-slate-700'}`}>
                            <div className="flex items-center">
                                {group.enabled === false && <PauseCircle size={20} className="mr-2" />}
                                <span>{group.enabled === false ? `${group.name} - PAUSED` : group.name}</span>
                            </div>
                            <span className="text-xs text-slate-500 font-normal">{nodesToRender.length} nodes</span>
                        </h3>

                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {nodesToRender.map((configNode) => {
                                // Try to find checking results for this node
                                const statusNode = resultsMap.get(configNode.id);

                                // Default state (WAITING/Initializing) if no result yet
                                let nodeName = configNode.name;
                                let nodeIp = configNode.ip;
                                let status = "WAITING";
                                let latency = null;
                                let isUp = false;
                                let isPending = false;
                                let isPaused = false;

                                // Color / Icon defaults for WAITING
                                let statusColor = 'text-slate-400';
                                let bgColor = 'bg-slate-700/20'; // Greyed out
                                let icon = <Clock size={20} className="animate-pulse" />;
                                let borderColor = 'border-slate-700/50';

                                if (statusNode) {
                                    // We have data!
                                    nodeName = statusNode.node_name;
                                    nodeIp = statusNode.ip;
                                    status = statusNode.status;
                                    latency = statusNode.latency;

                                    isUp = status === 'UP';
                                    isPending = status === 'PENDING';
                                    isPaused = status === 'PAUSED';

                                    if (isUp) {
                                        statusColor = 'text-green-400';
                                        bgColor = 'bg-green-500/20';
                                        icon = <Wifi size={20} />;
                                    } else if (isPending) {
                                        statusColor = 'text-orange-400';
                                        bgColor = 'bg-orange-500/20';
                                        icon = <Clock size={20} />;
                                    } else if (isPaused) {
                                        statusColor = 'text-slate-500';
                                        bgColor = 'bg-slate-700/30';
                                        icon = <PauseCircle size={20} />;
                                        // Paused is also grey-ish but distinct from Waiting
                                    } else {
                                        // DOWN
                                        statusColor = 'text-red-400';
                                        bgColor = 'bg-red-500/20';
                                        icon = <WifiOff size={20} />;
                                        borderColor = 'border-red-500/20';
                                    }
                                }

                                return (
                                    <div key={configNode.id} className={`bg-slate-800/50 rounded-lg p-3 grid grid-cols-12 items-center gap-2 hover:bg-slate-800 transition-colors border ${borderColor}`}>
                                        <div className="col-span-8 flex items-center space-x-3 min-w-0">
                                            <div className={`p-2 rounded-full flex-shrink-0 ${bgColor} ${statusColor}`}>
                                                {icon}
                                            </div>
                                            <div className="min-w-0">
                                                <div className="font-medium text-slate-200 truncate">{nodeName}</div>
                                                <div className="text-xs text-slate-500 truncate">{nodeIp}</div>
                                                <div className="flex gap-1 mt-1">
                                                    {((statusNode ? statusNode.monitor_ping : configNode.monitor_ping)) && (
                                                        <span className="px-1.5 py-0.5 text-[10px] font-medium bg-blue-500/20 text-blue-400 rounded border border-blue-500/30">
                                                            PING
                                                        </span>
                                                    )}
                                                    {((statusNode ? statusNode.monitor_snmp : configNode.monitor_snmp)) && (
                                                        <span className="px-1.5 py-0.5 text-[10px] font-medium bg-purple-500/20 text-purple-400 rounded border border-purple-500/30">
                                                            SNMP
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>

                                        <div className="col-span-4 text-right">
                                            <div className={`text-sm font-bold ${statusColor}`}>
                                                {status}
                                                {isPending && statusNode && <span className="text-xs ml-1 opacity-75">({statusNode.retry_count || 0})</span>}
                                            </div>
                                            <div className="text-xs text-slate-500 flex items-center justify-end space-x-1">
                                                <Activity size={12} />
                                                <span>{latency ? Math.round(latency) : '-'}ms</span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

export default Dashboard;
