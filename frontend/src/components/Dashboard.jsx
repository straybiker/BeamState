import React, { useEffect, useState } from 'react';
import api from '../api';
import { Wifi, WifiOff, Clock, Activity } from 'lucide-react';

const Dashboard = () => {
    const [statusData, setStatusData] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchStatus = async () => {
        try {
            // Fetch pinger status which includes latest results
            const response = await api.get('/status');
            if (response.data && response.data.latest_results) {
                setStatusData(response.data.latest_results);
            }
        } catch (error) {
            console.error("Failed to fetch status:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, []);

    // Group data by group_name
    const groupedData = statusData.reduce((acc, item) => {
        if (!acc[item.group_name]) acc[item.group_name] = [];
        acc[item.group_name].push(item);
        return acc;
    }, {});

    if (loading && statusData.length === 0) return <div className="text-center p-10 text-slate-400">Loading Dashboard...</div>;

    return (
        <div className="space-y-8">
            <header className="mb-6">
                <h2 className="text-3xl font-bold text-slate-100">Network Dashboard</h2>
                <p className="text-slate-400">Real-time status of monitored devices</p>
            </header>

            {Object.keys(groupedData).length === 0 && (
                <div className="bg-surface p-6 rounded-lg text-center text-slate-400 border border-slate-700">
                    No devices configured. Go to Configuration to add devices.
                </div>
            )}

            {Object.entries(groupedData).map(([groupName, nodes]) => (
                <div key={groupName} className="bg-surface rounded-xl p-6 border border-slate-700 shadow-sm">
                    <h3 className="text-xl font-semibold mb-4 text-primary border-b border-slate-700 pb-2">{groupName}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {nodes.map((node) => {
                            const isUp = node.status === 'UP';
                            return (
                                <div key={node.node_id} className="bg-slate-800/50 rounded-lg p-4 flex items-center justify-between hover:bg-slate-800 transition-colors border border-slate-700/50">
                                    <div className="flex items-center space-x-3">
                                        <div className={`p-2 rounded-full ${isUp ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                            {isUp ? <Wifi size={20} /> : <WifiOff size={20} />}
                                        </div>
                                        <div>
                                            <div className="font-medium text-slate-200">{node.node_name}</div>
                                            <div className="text-xs text-slate-500">{node.ip}</div>
                                        </div>
                                    </div>

                                    <div className="text-right">
                                        <div className={`text-sm font-bold ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                                            {node.status}
                                        </div>
                                        <div className="text-xs text-slate-500 flex items-center justify-end space-x-1">
                                            <Activity size={12} />
                                            <span>{node.latency ? Math.round(node.latency) : '-'}ms</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            ))}
        </div>
    );
};

export default Dashboard;
