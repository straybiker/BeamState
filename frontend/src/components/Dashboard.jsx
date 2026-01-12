import React, { useEffect, useState } from 'react';
import api from '../api';
import { Wifi, WifiOff, Clock, Activity, PauseCircle, FilterX } from 'lucide-react';
import toast from 'react-hot-toast';

const Dashboard = () => {
    const [statusData, setStatusData] = useState([]);
    const [groups, setGroups] = useState([]); // Store groups configuration
    const [loading, setLoading] = useState(true);
    const [activeFilter, setActiveFilter] = useState(null);

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

    // Helper to determine node status
    const getNodeStatus = (node, statusNode, groupEnabled) => {
        if (statusNode) return statusNode.status;
        if (groupEnabled === false) return 'PAUSED';
        return 'WAITING';
    };

    const toggleFilter = (filter) => {
        if (activeFilter === filter) setActiveFilter(null);
        else setActiveFilter(filter);
    };

    if (loading && groups.length === 0) return <div className="text-center p-10 text-slate-400">Loading Dashboard...</div>;

    // Calculate stats ensuring consistency
    let stats = { up: 0, down: 0, warning: 0, paused: 0, total: 0 };
    groups.forEach(group => {
        const groupResults = resultsByGroup[group.name] || [];
        const resultsMap = new Map(groupResults.map(r => [r.node_id, r]));
        const nodes = group.nodes || [];

        nodes.forEach(node => {
            stats.total++;
            const statusNode = resultsMap.get(node.id);
            const status = getNodeStatus(node, statusNode, group.enabled);

            if (status === 'UP') stats.up++;
            else if (status === 'DOWN') stats.down++;
            else if (status === 'PENDING') stats.warning++;
            else if (status === 'PAUSED') stats.paused++;
        });
    });

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

            {/* Summary Stats / Filter Controls */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <div
                    onClick={() => toggleFilter('UP')}
                    className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${activeFilter === 'UP' ? 'bg-green-500/10 border-green-500/50 ring-1 ring-green-500/50' : 'bg-slate-800/50 border-slate-700/50 hover:bg-slate-800'}`}
                >
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-green-500/10">
                            <Wifi size={20} className="text-green-400" />
                        </div>
                        <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Up</div>
                    </div>
                    <div className="text-2xl font-bold text-green-400 leading-none">{stats.up}</div>
                </div>

                <div
                    onClick={() => toggleFilter('DOWN')}
                    className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${activeFilter === 'DOWN' ? 'bg-red-500/10 border-red-500/50 ring-1 ring-red-500/50' : 'bg-slate-800/50 border-slate-700/50 hover:bg-slate-800'}`}
                >
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-red-500/10">
                            <WifiOff size={20} className="text-red-400" />
                        </div>
                        <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Down</div>
                    </div>
                    <div className="text-2xl font-bold text-red-400 leading-none">{stats.down}</div>
                </div>

                <div
                    onClick={() => toggleFilter('PENDING')}
                    className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${activeFilter === 'PENDING' ? 'bg-orange-500/10 border-orange-500/50 ring-1 ring-orange-500/50' : 'bg-slate-800/50 border-slate-700/50 hover:bg-slate-800'}`}
                >
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-orange-500/10">
                            <Clock size={20} className="text-orange-400" />
                        </div>
                        <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Warning</div>
                    </div>
                    <div className="text-2xl font-bold text-orange-400 leading-none">{stats.warning}</div>
                </div>

                <div
                    onClick={() => toggleFilter('PAUSED')}
                    className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${activeFilter === 'PAUSED' ? 'bg-slate-500/10 border-slate-500/50 ring-1 ring-slate-500/50' : 'bg-slate-800/50 border-slate-700/50 hover:bg-slate-800'}`}
                >
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-slate-500/10">
                            <PauseCircle size={20} className="text-slate-400" />
                        </div>
                        <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider">Paused</div>
                    </div>
                    <div className="text-2xl font-bold text-slate-400 leading-none">{stats.paused}</div>
                </div>
            </div>

            {activeFilter && (
                <div className="flex items-center justify-between bg-blue-500/10 border border-blue-500/20 px-4 py-2 rounded-lg text-blue-200 text-sm">
                    <span>Showing <strong>{activeFilter}</strong> nodes only</span>
                    <button onClick={() => setActiveFilter(null)} className="flex items-center hover:text-white transition-colors">
                        <FilterX size={16} className="mr-1" /> Clear Filter
                    </button>
                </div>
            )}

            {groups.length === 0 && (
                <div className="bg-surface p-6 rounded-lg text-center text-slate-400 border border-slate-700">
                    No groups configured. Go to Configuration to add groups.
                </div>
            )}

            {groups.map((group) => {
                const groupResults = resultsByGroup[group.name] || [];
                const resultsMap = new Map(groupResults.map(r => [r.node_id, r]));
                let nodesToRender = group.nodes || [];

                // Pre-process nodes to determine status and filter
                const processedNodes = nodesToRender.map(node => {
                    const statusNode = resultsMap.get(node.id);
                    const status = getNodeStatus(node, statusNode, group.enabled);
                    return { ...node, status, statusNode };
                });

                if (activeFilter) {
                    nodesToRender = processedNodes.filter(n => n.status === activeFilter);
                } else {
                    nodesToRender = processedNodes;
                }

                // If no nodes match filter, don't show group unless it's genuinely empty AND no filter active?
                // Actually if filter is active and group has no matching nodes, we probably shouldn't show the group content,
                // or show "No [FILTER] nodes in this group".
                // Prefer showing the group header but 0 nodes if filtered.

                // If group has no configured nodes AT ALL (empty group)
                if ((group.nodes || []).length === 0) {
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

                // If filtered result is empty
                if (nodesToRender.length === 0) {
                    // But if we are filtering, we might still want to show the group if we want to confirm "Group X has 0 Down nodes".
                    // Let's just hide the group if it has 0 nodes matching the filter to reduce clutter? 
                    // No, user might want to see which groups are fine. 
                    // Let's render header and "No nodes match filter".

                    // If we want to hide groups entirely when they don't have matching nodes:
                    // if (activeFilter && nodesToRender.length === 0) return null; 

                    // Let's stick to "No nodes match" to avoid layout jumping too much.
                }

                return (
                    <div key={group.id} className={`rounded-xl p-6 border shadow-sm transition-colors ${group.enabled === false ? 'bg-slate-900 border-slate-800 opacity-60' : 'bg-surface border-slate-700'}`}>
                        <h3 className={`text-xl font-semibold mb-4 border-b pb-2 flex justify-between items-center ${group.enabled === false ? 'text-slate-500 border-slate-800' : 'text-primary border-slate-700'}`}>
                            <div className="flex items-center">
                                {group.enabled === false && <PauseCircle size={20} className="mr-2" />}
                                <span>{group.enabled === false ? `${group.name} - PAUSED` : group.name}</span>
                            </div>
                            <span className="text-xs text-slate-500 font-normal">
                                {activeFilter ? `${nodesToRender.length}/${(group.nodes || []).length} ${activeFilter.toLowerCase()}` : `${nodesToRender.length} nodes`}
                            </span>
                        </h3>

                        {nodesToRender.length === 0 ? (
                            <div className="text-center py-4 text-slate-500 text-sm italic">
                                No nodes match filter "{activeFilter}"
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {nodesToRender.map((nodeData) => {
                                    const { status, statusNode, ...configNode } = nodeData;

                                    let nodeName = statusNode ? statusNode.node_name : configNode.name;
                                    let nodeIp = statusNode ? statusNode.ip : configNode.ip;
                                    let latency = statusNode ? statusNode.latency : null;

                                    let statusColor = 'text-slate-400';
                                    let bgColor = 'bg-slate-700/20'; // Greyed out
                                    let icon = <Clock size={20} className="animate-pulse" />;
                                    let borderColor = 'border-slate-700/50';

                                    const isUp = status === 'UP';
                                    const isPending = status === 'PENDING';
                                    const isPaused = status === 'PAUSED';

                                    if (isUp) {
                                        statusColor = 'text-green-400';
                                        bgColor = 'bg-green-500/20';
                                        icon = <Wifi size={20} />;
                                        borderColor = 'border-slate-700/50';
                                    } else if (isPending) {
                                        statusColor = 'text-orange-400';
                                        bgColor = 'bg-orange-500/20';
                                        icon = <Clock size={20} />;
                                        borderColor = 'border-slate-700/50';
                                    } else if (isPaused) {
                                        statusColor = 'text-slate-500';
                                        bgColor = 'bg-slate-700/30';
                                        icon = <PauseCircle size={20} />;
                                        borderColor = 'border-slate-700/50';
                                    } else if (status === 'DOWN') {
                                        statusColor = 'text-red-400';
                                        bgColor = 'bg-red-500/20';
                                        icon = <WifiOff size={20} />;
                                        borderColor = 'border-red-500/20';
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
                        )}
                    </div>
                );
            })}
        </div>
    );
};

export default Dashboard;
