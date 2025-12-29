import React, { useEffect, useState } from 'react';
import api from '../api';
import { Plus, Trash2, ArrowUpDown } from 'lucide-react';
import toast from 'react-hot-toast';

const Config = () => {
    const [groups, setGroups] = useState([]);
    const [nodes, setNodes] = useState([]);
    const [activeTab, setActiveTab] = useState('nodes'); // 'nodes' or 'groups'

    // Forms
    const [newGroup, setNewGroup] = useState({ name: '', interval: 60, packet_count: 1 });
    const [newNode, setNewNode] = useState({ name: '', ip: '', group_id: '', interval: '', packet_count: '' });

    const fetchData = async () => {
        try {
            const gRes = await api.get('/config/groups');
            const nRes = await api.get('/config/nodes');
            setGroups(gRes.data);
            setNodes(nRes.data);
        } catch (error) {
            console.error("Error fetching config:", error);
            toast.error("Failed to load configuration");
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleCreateGroup = async (e) => {
        e.preventDefault();
        try {
            await api.post('/config/groups', newGroup);
            setNewGroup({ name: '', interval: 60, packet_count: 1 });
            toast.success("Group created successfully");
            fetchData();
        } catch (err) {
            let message = "Failed to create group";
            if (err.response?.data?.detail) {
                const detail = err.response.data.detail;
                if (Array.isArray(detail)) {
                    message = detail.map(d => d.msg).join(', ');
                } else {
                    message = detail;
                }
            }
            toast.error(message);
        }
    };

    const handleCreateNode = async (e) => {
        e.preventDefault();
        try {
            const payload = { ...newNode };
            // Clean up empty strings to null/int
            if (!payload.group_id) { toast.error("Group is required"); return; }
            // payload.group_id is now a UUID string, do not parse!

            payload.interval = payload.interval ? parseInt(payload.interval) : null;
            payload.packet_count = payload.packet_count ? parseInt(payload.packet_count) : null;

            await api.post('/config/nodes', payload);
            setNewNode({ name: '', ip: '', group_id: '', interval: '', packet_count: '' });
            toast.success("Node created successfully");
            fetchData();
        } catch (err) {
            let message = "Failed to create node";
            if (err.response?.data?.detail) {
                const detail = err.response.data.detail;
                if (Array.isArray(detail)) {
                    message = detail.map(d => d.msg).join(', ');
                } else {
                    message = detail;
                }
            }
            toast.error(message);
        }
    };

    const handleDeleteNode = async (id) => {
        if (!confirm("Delete node?")) return;
        try {
            await api.delete(`/config/nodes/${id}`);
            toast.success("Node deleted");
            fetchData();
        } catch (e) {
            toast.error("Failed to delete node");
        }
    };

    const handleDeleteGroup = async (id) => {
        if (!confirm("Delete group and all its nodes?")) return;
        try {
            await api.delete(`/config/groups/${id}`);
            toast.success("Group deleted");
            fetchData();
        } catch (e) {
            toast.error("Failed to delete group");
        }
    };

    // Sorting Logic
    const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

    const requestSort = (key) => {
        let direction = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };

    const getSortedGroups = () => {
        let sortableItems = [...groups];
        if (sortConfig.key) {
            sortableItems.sort((a, b) => {
                let aVal = a[sortConfig.key];
                let bVal = b[sortConfig.key];

                // Numeric Sort for Interval
                if (sortConfig.key === 'interval') {
                    return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
                }

                if (typeof aVal === 'string') aVal = aVal.toLowerCase();
                if (typeof bVal === 'string') bVal = bVal.toLowerCase();

                if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return sortableItems;
    };

    const getSortedNodes = () => {
        let sortableItems = [...nodes];
        if (sortConfig.key) {
            sortableItems.sort((a, b) => {
                let aVal = a[sortConfig.key];
                let bVal = b[sortConfig.key];

                // Special handling: Group Name sorting
                if (sortConfig.key === 'group') {
                    const gA = groups.find(g => g.id === a.group_id);
                    const gB = groups.find(g => g.id === b.group_id);
                    aVal = gA ? gA.name : '';
                    bVal = gB ? gB.name : '';
                }

                // Special handling: Effective Interval sorting
                if (sortConfig.key === 'interval') {
                    const gA = groups.find(g => g.id === a.group_id);
                    const gB = groups.find(g => g.id === b.group_id);

                    // Use node interval if set, otherwise group interval
                    const valA = a.interval !== null && a.interval !== undefined ? a.interval : (gA ? gA.interval : 0);
                    const valB = b.interval !== null && b.interval !== undefined ? b.interval : (gB ? gB.interval : 0);

                    return sortConfig.direction === 'asc' ? valA - valB : valB - valA;
                }

                // Special handling: IP Address sorting
                if (sortConfig.key === 'ip') {
                    // Use localeCompare with numeric option for "smart" IP sorting (1.2.3.4 vs 1.2.3.10)
                    return sortConfig.direction === 'asc'
                        ? aVal.localeCompare(bVal, undefined, { numeric: true })
                        : bVal.localeCompare(aVal, undefined, { numeric: true });
                }

                // Default String/Alpha sorting
                if (typeof aVal === 'string') aVal = aVal.toLowerCase();
                if (typeof bVal === 'string') bVal = bVal.toLowerCase();

                if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }
        return sortableItems;
    };

    return (
        <div className="space-y-6">
            <header className="flex items-center justify-between mb-8">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">Configuration</h2>
                    <p className="text-slate-400">Manage groups and nodes</p>
                </div>
            </header>

            {/* Tabs */}
            <div className="flex space-x-1 bg-surface p-1 rounded-lg w-fit border border-slate-700">
                <button
                    onClick={() => setActiveTab('nodes')}
                    className={`px-4 py-2 rounded-md transition-all ${activeTab === 'nodes' ? 'bg-primary text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                >Nodes</button>
                <button
                    onClick={() => setActiveTab('groups')}
                    className={`px-4 py-2 rounded-md transition-all ${activeTab === 'groups' ? 'bg-primary text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                >Groups</button>
            </div>

            {activeTab === 'groups' && (
                <div className="bg-surface p-6 rounded-xl border border-slate-700 shadow-sm space-y-6">
                    <h3 className="text-xl font-semibold text-slate-100">Groups</h3>

                    {/* Create Group Form */}
                    <form onSubmit={handleCreateGroup} className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end bg-slate-800/50 p-4 rounded-lg border border-slate-700/50">
                        <div className="col-span-1 md:col-span-2">
                            <label className="block text-sm font-medium text-slate-400 mb-1">Group Name</label>
                            <input
                                type="text"
                                required
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newGroup.name} onChange={e => setNewGroup({ ...newGroup, name: e.target.value })}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-400 mb-1">Ping Interval (s)</label>
                            <input
                                type="number"
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newGroup.interval} onChange={e => setNewGroup({ ...newGroup, interval: parseInt(e.target.value) })}
                            />
                        </div>
                        <div className="flex justify-end">
                            <button type="submit" className="flex items-center justify-center bg-primary hover:bg-blue-600 text-white px-4 py-2 rounded-md w-full md:w-auto transition-colors">
                                <Plus size={18} className="mr-2" /> Add Group
                            </button>
                        </div>
                    </form>

                    {/* Groups List */}
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-slate-800/50 text-slate-400 text-sm uppercase">
                                <tr>
                                    <th className="px-4 py-3 rounded-tl-lg cursor-pointer hover:text-white" onClick={() => requestSort('name')}>
                                        <div className="flex items-center">Name <ArrowUpDown size={14} className="ml-1" /></div>
                                    </th>
                                    <th className="px-4 py-3 cursor-pointer hover:text-white" onClick={() => requestSort('interval')}>
                                        <div className="flex items-center">Default Interval <ArrowUpDown size={14} className="ml-1" /></div>
                                    </th>
                                    <th className="px-4 py-3 rounded-tr-lg text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700">
                                {getSortedGroups().map(g => (
                                    <tr key={g.id} className="hover:bg-slate-800/30 transition-colors">
                                        <td className="px-4 py-3 font-medium">{g.name}</td>
                                        <td className="px-4 py-3">{g.interval}s</td>
                                        <td className="px-4 py-3 text-right">
                                            <button onClick={() => handleDeleteGroup(g.id)} className="text-red-400 hover:text-red-300 p-1 rounded transition-colors"><Trash2 size={18} /></button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {groups.length === 0 && <div className="p-4 text-center text-slate-500">No groups defined.</div>}
                    </div>
                </div>
            )}

            {activeTab === 'nodes' && (
                <div className="bg-surface p-6 rounded-xl border border-slate-700 shadow-sm space-y-6">
                    <h3 className="text-xl font-semibold text-slate-100">Nodes</h3>

                    {/* Create Node Form */}
                    <form onSubmit={handleCreateNode} className="grid grid-cols-1 md:grid-cols-12 gap-4 items-end bg-slate-800/50 p-4 rounded-lg border border-slate-700/50">
                        <div className="col-span-1 md:col-span-3">
                            <label className="block text-sm font-medium text-slate-400 mb-1">Name</label>
                            <input
                                type="text" required
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newNode.name} onChange={e => setNewNode({ ...newNode, name: e.target.value })}
                            />
                        </div>
                        <div className="col-span-1 md:col-span-3">
                            <label className="block text-sm font-medium text-slate-400 mb-1">IP Address</label>
                            <input
                                type="text" required
                                placeholder="192.168.1.1"
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newNode.ip} onChange={e => setNewNode({ ...newNode, ip: e.target.value })}
                            />
                        </div>
                        <div className="col-span-1 md:col-span-2">
                            <label className="block text-sm font-medium text-slate-400 mb-1">Group</label>
                            <select
                                required
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newNode.group_id} onChange={e => setNewNode({ ...newNode, group_id: e.target.value })}
                            >
                                <option value="">Select...</option>
                                {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                            </select>
                        </div>
                        <div className="col-span-1 md:col-span-2">
                            <label className="block text-sm font-medium text-slate-400 mb-1">Interval (Opt)</label>
                            <input
                                type="number"
                                placeholder="Def"
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newNode.interval} onChange={e => setNewNode({ ...newNode, interval: e.target.value })}
                            />
                        </div>
                        <div className="col-span-1 md:col-span-2 flex justify-end">
                            <button type="submit" className="bg-primary hover:bg-blue-600 text-white px-4 py-2 rounded-md w-full transition-colors flex items-center justify-center">
                                <Plus size={18} className="mr-2" /> Add
                            </button>
                        </div>
                    </form>

                    {/* Nodes List */}
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-slate-800/50 text-slate-400 text-sm uppercase">
                                <tr>
                                    <th className="px-4 py-3 rounded-tl-lg cursor-pointer hover:text-white" onClick={() => requestSort('name')}>
                                        <div className="flex items-center">Name <ArrowUpDown size={14} className="ml-1" /></div>
                                    </th>
                                    <th className="px-4 py-3 cursor-pointer hover:text-white" onClick={() => requestSort('ip')}>
                                        <div className="flex items-center">IP <ArrowUpDown size={14} className="ml-1" /></div>
                                    </th>
                                    <th className="px-4 py-3 cursor-pointer hover:text-white" onClick={() => requestSort('group')}>
                                        <div className="flex items-center">Group <ArrowUpDown size={14} className="ml-1" /></div>
                                    </th>
                                    <th className="px-4 py-3 cursor-pointer hover:text-white" onClick={() => requestSort('interval')}>
                                        <div className="flex items-center">Interval <ArrowUpDown size={14} className="ml-1" /></div>
                                    </th>
                                    <th className="px-4 py-3 rounded-tr-lg text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700">
                                {getSortedNodes().map(n => {
                                    const group = groups.find(g => g.id === n.group_id);
                                    return (
                                        <tr key={n.id} className="hover:bg-slate-800/30 transition-colors">
                                            <td className="px-4 py-3 font-medium">{n.name}</td>
                                            <td className="px-4 py-3 text-slate-400">{n.ip}</td>
                                            <td className="px-4 py-3"><span className="bg-slate-700 text-slate-300 text-xs px-2 py-1 rounded-full">{group ? group.name : 'Unknown'}</span></td>
                                            <td className="px-4 py-3 text-slate-400">
                                                {n.interval ? (
                                                    `${n.interval}s`
                                                ) : (
                                                    group ? (
                                                        <span className="text-slate-500">{group.interval}s <span className="text-xs text-slate-600">(default)</span></span>
                                                    ) : 'Def'
                                                )}
                                            </td>
                                            <td className="px-4 py-3 text-right">
                                                <button onClick={() => handleDeleteNode(n.id)} className="text-red-400 hover:text-red-300 p-1 rounded transition-colors"><Trash2 size={18} /></button>
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                        {nodes.length === 0 && <div className="p-4 text-center text-slate-500">No nodes defined.</div>}
                    </div>
                </div>
            )}
        </div>
    );
};

export default Config;
