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
        const interval = setInterval(fetchStatusOnly, 5000); // Poll status every 5s
        return () => clearInterval(interval);
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
                    <h2 className="text-3xl font-bold text-slate-100">Network Dashboard</h2>
                    <p className="text-slate-400">Real-time status of monitored devices</p>
                </div>
                <img
                    src="/logo_transparant.png"
                    alt="BeamState Logo"
                    className="h-16 object-contain"
                />
            </header>

            {groups.length === 0 && (
                <div className="bg-surface p-6 rounded-lg text-center text-slate-400 border border-slate-700">
                    No groups configured. Go to Configuration to add groups.
                </div>
            )}

            {groups.map((group) => {
                // Get results for this group's name
                // Note: Pinger results use group name. We assume names are unique.
                // Alternatively, we could map nodes by ID if we had them, but name is used in existing logic.
                const groupNodes = resultsByGroup[group.name] || [];

                // If the group has configured nodes but no results yet (app just started),
                // we might want to show them as "Initializing" or just wait.
                // But for "Empty Group" feature, we care if group.nodes is empty.
                const configNodeCount = group.nodes ? group.nodes.length : 0;

                return (
                    <div key={group.id} className={`rounded-xl p-6 border shadow-sm transition-colors ${group.enabled === false ? 'bg-slate-900 border-slate-800 opacity-60' : 'bg-surface border-slate-700'}`}>
                        <h3 className={`text-xl font-semibold mb-4 border-b pb-2 flex justify-between items-center ${group.enabled === false ? 'text-slate-500 border-slate-800' : 'text-primary border-slate-700'}`}>
                            <div className="flex items-center">
                                {group.enabled === false && <PauseCircle size={20} className="mr-2" />}
                                <span>{group.enabled === false ? `${group.name} - PAUSED` : group.name}</span>
                            </div>
                            <span className="text-xs text-slate-500 font-normal">{configNodeCount} nodes</span>
                        </h3>

                        {configNodeCount === 0 ? (
                            <div className="text-center py-8 text-slate-500 bg-slate-800/20 rounded-lg border border-dashed border-slate-700">
                                This group is empty
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {groupNodes.map((node) => {
                                    const isUp = node.status === 'UP';
                                    const isPending = node.status === 'PENDING';
                                    const isPaused = node.status === 'PAUSED';

                                    let statusColor = 'text-red-400';
                                    let bgColor = 'bg-red-500/20';
                                    let icon = <WifiOff size={20} />;

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
                                    }

                                    return (
                                        <div key={node.node_id} className="bg-slate-800/50 rounded-lg p-4 flex items-center justify-between hover:bg-slate-800 transition-colors border border-slate-700/50">
                                            <div className="flex items-center space-x-3">
                                                <div className={`p-2 rounded-full ${bgColor} ${statusColor}`}>
                                                    {icon}
                                                </div>
                                                <div>
                                                    <div className="font-medium text-slate-200">{node.node_name}</div>
                                                    <div className="text-xs text-slate-500">{node.ip}</div>
                                                </div>
                                            </div>

                                            <div className="text-right">
                                                <div className={`text-sm font-bold ${statusColor}`}>
                                                    {node.status}
                                                    {isPending && <span className="text-xs ml-1 opacity-75">({node.retry_count || 0})</span>}
                                                </div>
                                                <div className="text-xs text-slate-500 flex items-center justify-end space-x-1">
                                                    <Activity size={12} />
                                                    <span>{node.latency ? Math.round(node.latency) : '-'}ms</span>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                                {groupNodes.length === 0 && configNodeCount > 0 && (
                                    <div className="col-span-full text-center py-4 text-slate-500 animate-pulse">
                                        Waiting for ping results...
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
};

export default Dashboard;
