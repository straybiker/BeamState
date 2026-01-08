import React, { useEffect, useState } from 'react';
import api from '../api';
import { Plus, Trash2, ArrowUpDown, Play, Pause } from 'lucide-react';
import toast from 'react-hot-toast';
import MetricsConfig from './MetricsConfig';
import AppConfig from './AppConfig';

const Config = () => {
    const [groups, setGroups] = useState([]);
    const [nodes, setNodes] = useState([]);
    const [activeTab, setActiveTab] = useState('nodes'); // 'nodes' or 'groups'

    // Filters for nodes list
    const [filterGroup, setFilterGroup] = useState('all');
    const [filterProtocol, setFilterProtocol] = useState('all');

    // Forms
    const [newGroup, setNewGroup] = useState({
        name: '',
        interval: 60,
        packet_count: 1,
        snmp_community: 'public',
        snmp_port: 161
    });
    const [newNode, setNewNode] = useState({
        name: '',
        ip: '',
        group_id: '',
        interval: '',
        packet_count: '',
        monitor_ping: true,
        monitor_snmp: false,
        snmp_community: '',
        snmp_port: '',
        notification_priority: null
    });
    const [editingNode, setEditingNode] = useState(null); // Track which node is being edited
    const [appConfig, setAppConfig] = useState({ pushover: { priority: 0 } }); // For default priority label

    const fetchData = async () => {
        try {
            const gRes = await api.get('/config/groups');
            const nRes = await api.get('/config/nodes');
            setGroups(gRes.data);
            setNodes(nRes.data);
            // Auto-select default group for new nodes
            const defaultGroup = gRes.data.find(g => g.is_default);
            if (defaultGroup && !editingNode) {
                setNewNode(prev => ({ ...prev, group_id: prev.group_id || defaultGroup.id }));
            }
            // Fetch app config for default priority label
            try {
                const appRes = await api.get('/config/app');
                setAppConfig(appRes.data);
            } catch (e) { /* ignore */ }
        } catch (error) {
            console.error("Error fetching config:", error);
            toast.error("Failed to load configuration");
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    // Update selected group in Add Node form when default group changes
    useEffect(() => {
        if (!editingNode && groups.length > 0) {
            const defaultGroup = groups.find(g => g.is_default);
            if (defaultGroup) {
                setNewNode(prev => ({ ...prev, group_id: defaultGroup.id }));
            }
        }
    }, [groups, editingNode]);

    const handleCreateGroup = async (e) => {
        e.preventDefault();
        try {
            await api.post('/config/groups', newGroup);
            setNewGroup({
                name: '',
                interval: 60,
                packet_count: 1,
                snmp_community: 'public',
                snmp_port: 161
            });
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

    const handleCreateOrUpdateNode = async (e) => {
        e.preventDefault();
        try {
            const payload = { ...newNode };
            // Clean up empty strings to null/int
            if (!payload.group_id) { toast.error("Group is required"); return; }

            payload.interval = payload.interval ? parseInt(payload.interval) : null;
            payload.packet_count = payload.packet_count ? parseInt(payload.packet_count) : null;
            payload.snmp_community = payload.snmp_community || null;
            payload.snmp_port = payload.snmp_port ? parseInt(payload.snmp_port) : null;

            // Validate that at least one protocol is enabled
            if (!payload.monitor_ping && !payload.monitor_snmp) {
                toast.error("At least one monitoring protocol (PING or SNMP) must be enabled");
                return;
            }

            if (editingNode) {
                // Update existing node
                await api.put(`/config/nodes/${editingNode.id}`, payload);
                toast.success("Node updated successfully");
            } else {
                // Create new node
                await api.post('/config/nodes', payload);
                toast.success("Node created successfully");
            }

            // Reset form
            setNewNode({
                name: '',
                ip: '',
                group_id: '',
                interval: '',
                packet_count: '',
                monitor_ping: true,
                monitor_snmp: false,
                snmp_community: '',
                snmp_port: ''
            });
            setEditingNode(null);
            fetchData();
        } catch (err) {
            let message = editingNode ? "Failed to update node" : "Failed to create node";
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

    const handleEditNode = (node) => {
        // If clicking the same node, cancel edit mode
        if (editingNode && editingNode.id === node.id) {
            handleCancelEdit();
            return;
        }
        setEditingNode(node);
        setNewNode({
            name: node.name,
            ip: node.ip,
            group_id: node.group_id,
            interval: node.interval !== null ? node.interval.toString() : '',
            packet_count: node.packet_count !== null ? node.packet_count.toString() : '',
            monitor_ping: node.monitor_ping !== null ? node.monitor_ping : true,
            monitor_snmp: node.monitor_snmp !== null ? node.monitor_snmp : false,
            snmp_community: node.snmp_community || '',
            snmp_port: node.snmp_port !== null ? node.snmp_port.toString() : '',
            notification_priority: node.notification_priority !== null ? node.notification_priority : null
        });
    };

    const handleCancelEdit = () => {
        setEditingNode(null);
        setNewNode({
            name: '',
            ip: '',
            group_id: '',
            interval: '',
            packet_count: '',
            monitor_ping: true,
            monitor_snmp: false,
            snmp_community: '',
            snmp_port: '',
            notification_priority: null
        });
    };

    const [deleteConfirm, setDeleteConfirm] = useState({ type: null, id: null });

    const handleDeleteNode = async (id) => {
        if (deleteConfirm.type === 'node' && deleteConfirm.id === id) {
            // Confirmed
            try {
                await api.delete(`/config/nodes/${id}`);
                toast.success("Node deleted");
                setDeleteConfirm({ type: null, id: null });
                fetchData();
            } catch (e) {
                toast.error("Failed to delete node");
            }
        } else {
            // First click
            setDeleteConfirm({ type: 'node', id });
            // Auto-reset after 3 seconds
            setTimeout(() => setDeleteConfirm(prev => prev.id === id ? { type: null, id: null } : prev), 3000);
        }
    };

    const handleDeleteGroup = async (id) => {
        if (deleteConfirm.type === 'group' && deleteConfirm.id === id) {
            try {
                await api.delete(`/config/groups/${id}`);
                toast.success("Group deleted");
                setDeleteConfirm({ type: null, id: null });
                fetchData();
            } catch (e) {
                toast.error("Failed to delete group");
            }
        } else {
            setDeleteConfirm({ type: 'group', id });
            setTimeout(() => setDeleteConfirm(prev => prev.id === id ? { type: null, id: null } : prev), 3000);
        }
    };


    const handleToggleGroup = async (group) => {
        try {
            // Optimistic update or wait? Wait is safer.
            const newEnabled = group.enabled === false ? true : false;
            await api.put(`/config/groups/${group.id}`, { ...group, enabled: newEnabled });
            toast.success(`Group ${newEnabled ? 'started' : 'paused'}`);
            fetchData();
        } catch (e) {
            console.error(e);
            toast.error("Failed to update group status");
        }
    };

    const handleToggleDefault = async (group) => {
        try {
            // Toggle: if already default, unset; otherwise set as default
            const newIsDefault = !group.is_default;
            await api.put(`/config/groups/${group.id}`, { ...group, is_default: newIsDefault });
            toast.success(newIsDefault ? `${group.name} set as default` : `Default group cleared`);
            fetchData();
        } catch (e) {
            console.error(e);
            toast.error("Failed to update default group");
        }
    };

    const handleToggleNode = async (node) => {
        try {
            const newEnabled = node.enabled === false ? true : false;
            await api.put(`/config/nodes/${node.id}`, { ...node, enabled: newEnabled });
            toast.success(`Node ${newEnabled ? 'started' : 'paused'}`);
            fetchData();
        } catch (e) {
            console.error(e);
            toast.error("Failed to update node status");
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
            <header className="flex flex-col md:flex-row md:items-center justify-between mb-6 gap-4">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">Configuration</h2>
                </div>

                <div className="flex items-center gap-6">
                    {/* Tabs moved to Header */}
                    <div className="flex space-x-1 bg-surface p-1 rounded-lg border border-slate-700">
                        <button
                            onClick={() => setActiveTab('nodes')}
                            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${activeTab === 'nodes' ? 'bg-primary text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                        >Nodes</button>
                        <button
                            onClick={() => setActiveTab('metrics')}
                            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${activeTab === 'metrics' ? 'bg-primary text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                        >SNMP</button>
                        <button
                            onClick={() => setActiveTab('groups')}
                            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${activeTab === 'groups' ? 'bg-primary text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                        >Groups</button>
                        <button
                            onClick={() => setActiveTab('settings')}
                            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${activeTab === 'settings' ? 'bg-primary text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                        >Settings</button>
                    </div>

                    <img
                        src="/logo_transparant.png"
                        alt="BeamState Logo"
                        className="h-16 object-contain hidden md:block"
                    />
                </div>
            </header>

            {activeTab === 'groups' && (
                <div className="bg-surface p-6 rounded-xl border border-slate-700 shadow-sm space-y-6">
                    <h3 className="text-xl font-semibold text-slate-100">Groups</h3>

                    {/* Create Group Form */}
                    <form onSubmit={handleCreateGroup} className="grid grid-cols-1 md:grid-cols-6 gap-4 items-end bg-slate-800/50 p-4 rounded-lg border border-slate-700/50">
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
                            <label className="block text-sm font-medium text-slate-400 mb-1">Interval (s)</label>
                            <input
                                type="number"
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newGroup.interval} onChange={e => setNewGroup({ ...newGroup, interval: parseInt(e.target.value) })}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-400 mb-1">SNMP Community</label>
                            <input
                                type="text"
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newGroup.snmp_community} onChange={e => setNewGroup({ ...newGroup, snmp_community: e.target.value })}
                                placeholder="public"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-400 mb-1">SNMP Port</label>
                            <input
                                type="number"
                                className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                value={newGroup.snmp_port} onChange={e => setNewGroup({ ...newGroup, snmp_port: parseInt(e.target.value) })}
                                placeholder="161"
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
                                    <th className="px-4 py-3 text-center">Default</th>
                                    <th className="px-4 py-3 rounded-tr-lg text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700">
                                {getSortedGroups().map(g => (
                                    <tr key={g.id} className="hover:bg-slate-800/30 transition-colors">
                                        <td className="px-4 py-3 font-medium">{g.name}</td>
                                        <td className="px-4 py-3">{g.interval}s</td>
                                        <td className="px-4 py-3 text-center">
                                            <input
                                                type="radio"
                                                name="defaultGroup"
                                                checked={g.is_default || false}
                                                onChange={() => handleToggleDefault(g)}
                                                className="w-4 h-4 cursor-pointer"
                                                style={{ accentColor: '#3b82f6' }}
                                            />
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            <div className="flex items-center justify-end gap-2">
                                                <button onClick={() => handleToggleGroup(g)} className="bg-slate-700/50 hover:bg-slate-700 p-1 rounded transition-colors" title={g.enabled === false ? "Start Group" : "Pause Group"}>
                                                    {g.enabled === false ? <Play size={18} className="text-green-400" /> : <Pause size={18} className="text-orange-400" />}
                                                </button>
                                                <button onClick={() => handleDeleteGroup(g.id)} className={`${deleteConfirm.type === 'group' && deleteConfirm.id === g.id ? 'bg-red-600 text-white px-2' : 'text-red-400 hover:text-red-300 p-1'} rounded transition-all flex items-center justify-center`}>
                                                    {deleteConfirm.type === 'group' && deleteConfirm.id === g.id ? <span className="text-xs font-bold">Confirm</span> : <Trash2 size={18} />}
                                                </button>
                                            </div>
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
                    <div className="flex items-center justify-between">
                        <h3 className="text-xl font-semibold text-slate-100">
                            {editingNode ? `Edit Node: ${editingNode.name}` : 'Nodes'}
                        </h3>
                        <div className="flex gap-2">
                            {editingNode ? (
                                <>
                                    <button
                                        type="button"
                                        onClick={handleCancelEdit}
                                        className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-md transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button type="submit" form="nodeForm" className="bg-primary hover:bg-blue-600 text-white px-4 py-2 rounded-md transition-colors">
                                        Update Node
                                    </button>
                                </>
                            ) : (
                                <button type="submit" form="nodeForm" className="bg-primary hover:bg-blue-600 text-white px-4 py-2 rounded-md transition-colors flex items-center justify-center">
                                    <Plus size={18} className="mr-2" /> Add Node
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Create/Edit Node Form */}
                    <form id="nodeForm" onSubmit={handleCreateOrUpdateNode} className={`grid grid-cols-1 gap-4 p-4 rounded-lg border ${editingNode ? 'bg-blue-900/20 border-blue-500/30' : 'bg-slate-800/50 border-slate-700/50'}`}>
                        {/* Basic Info Row - Full Width */}
                        <div className="grid grid-cols-2 md:grid-cols-12 gap-4 items-end">
                            <div className="col-span-1 md:col-span-3">
                                <label className="block text-sm font-medium text-slate-400 mb-1">Name</label>
                                <input
                                    type="text" required
                                    className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                    value={newNode.name} onChange={e => setNewNode({ ...newNode, name: e.target.value })}
                                />
                            </div>
                            <div className="col-span-1 md:col-span-2">
                                <label className="block text-sm font-medium text-slate-400 mb-1">IP Address</label>
                                <input
                                    type="text" required
                                    placeholder="192.168.1.1"
                                    className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                    value={newNode.ip} onChange={e => setNewNode({ ...newNode, ip: e.target.value })}
                                />
                            </div>
                            <div className="col-span-1 md:col-span-3">
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
                                <label className="block text-sm font-medium text-slate-400 mb-1">Interval</label>
                                <input
                                    type="number"
                                    placeholder={groups.find(g => g.id === newNode.group_id)?.interval?.toString() || "Def"}
                                    className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                    value={newNode.interval} onChange={e => setNewNode({ ...newNode, interval: e.target.value })}
                                />
                            </div>
                            <div className="col-span-2 md:col-span-2">
                                <label className="block text-sm font-medium text-slate-400 mb-1">Alert Priority</label>
                                <select
                                    className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                    value={newNode.notification_priority === null ? '' : newNode.notification_priority}
                                    onChange={e => setNewNode({ ...newNode, notification_priority: e.target.value === '' ? null : parseInt(e.target.value) })}
                                >
                                    <option value="">Default ({appConfig?.pushover?.priority === -2 ? 'Lowest' : appConfig?.pushover?.priority === -1 ? 'Low' : appConfig?.pushover?.priority === 0 ? 'Normal' : appConfig?.pushover?.priority === 1 ? 'High' : appConfig?.pushover?.priority === 2 ? 'Emergency' : 'Normal'})</option>
                                    <option value="-2">-2 Lowest</option>
                                    <option value="-1">-1 Low</option>
                                    <option value="0">0 Normal</option>
                                    <option value="1">1 High</option>
                                    <option value="2">2 Emergency</option>
                                </select>
                            </div>
                        </div>

                        {/* Protocol Selection */}
                        <div className="border-t border-slate-700 pt-4">
                            <label className="block text-sm font-medium text-slate-400 mb-2">Monitoring Protocols</label>
                            <div className="flex gap-6">
                                <label className="flex items-center space-x-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={newNode.monitor_ping}
                                        onChange={e => setNewNode({ ...newNode, monitor_ping: e.target.checked })}
                                        className="w-4 h-4"
                                        style={{ accentColor: '#3b82f6' }}
                                    />
                                    <span className="text-white">ICMP Ping</span>
                                </label>
                                <label className="flex items-center space-x-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={newNode.monitor_snmp}
                                        onChange={e => setNewNode({ ...newNode, monitor_snmp: e.target.checked })}
                                        className="w-4 h-4"
                                        style={{ accentColor: '#3b82f6' }}
                                    />
                                    <span className="text-white">SNMP</span>
                                </label>
                            </div>
                        </div>

                        {/* SNMP Override Settings (conditional) */}
                        {newNode.monitor_snmp && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-900/50 p-4 rounded-lg border border-slate-700/50">
                                <div>
                                    <label className="block text-sm font-medium text-slate-400 mb-1">SNMP Community (Override)</label>
                                    <input
                                        type="text"
                                        className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                        value={newNode.snmp_community}
                                        onChange={e => setNewNode({ ...newNode, snmp_community: e.target.value })}
                                        placeholder="Leave empty to use group default"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-400 mb-1">SNMP Port (Override)</label>
                                    <input
                                        type="number"
                                        className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-2 text-white focus:ring-2 focus:ring-primary outline-none"
                                        value={newNode.snmp_port}
                                        onChange={e => setNewNode({ ...newNode, snmp_port: e.target.value })}
                                        placeholder="Leave empty to use group default"
                                    />
                                </div>
                            </div>
                        )}
                    </form>

                    {/* Filters */}
                    <div className="flex flex-wrap gap-3 items-center">
                        <div className="flex items-center space-x-2">
                            <label className="text-sm text-slate-400 font-medium">Group:</label>
                            <select
                                value={filterGroup}
                                onChange={(e) => setFilterGroup(e.target.value)}
                                className="bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-sm text-white focus:ring-2 focus:ring-primary outline-none"
                            >
                                <option value="all">All Groups</option>
                                {groups.map(g => (
                                    <option key={g.id} value={g.id}>{g.name}</option>
                                ))}
                            </select>
                        </div>
                        <div className="flex items-center space-x-2">
                            <label className="text-sm text-slate-400 font-medium">Protocol:</label>
                            <select
                                value={filterProtocol}
                                onChange={(e) => setFilterProtocol(e.target.value)}
                                className="bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-sm text-white focus:ring-2 focus:ring-primary outline-none"
                            >
                                <option value="all">All Protocols</option>
                                <option value="ping">PING Only</option>
                                <option value="snmp">SNMP Only</option>
                                <option value="both">Both PING & SNMP</option>
                            </select>
                        </div>
                        {(filterGroup !== 'all' || filterProtocol !== 'all') && (
                            <button
                                onClick={() => { setFilterGroup('all'); setFilterProtocol('all'); }}
                                className="text-xs text-slate-400 hover:text-white transition-colors underline"
                            >
                                Clear Filters
                            </button>
                        )}
                    </div>

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
                                    <th className="px-4 py-3">Protocols</th>
                                    <th className="px-4 py-3 rounded-tr-lg text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700">
                                {getSortedNodes().filter(n => {
                                    // Filter by group
                                    if (filterGroup !== 'all' && n.group_id !== filterGroup) return false;

                                    // Filter by protocol
                                    if (filterProtocol === 'ping' && (!n.monitor_ping || n.monitor_snmp)) return false;
                                    if (filterProtocol === 'snmp' && (!n.monitor_snmp || n.monitor_ping)) return false;
                                    if (filterProtocol === 'both' && !(n.monitor_ping && n.monitor_snmp)) return false;

                                    return true;
                                }).map(n => {
                                    const group = groups.find(g => g.id === n.group_id);
                                    const isEditing = editingNode?.id === n.id;
                                    return (
                                        <tr
                                            key={n.id}
                                            onClick={() => handleEditNode(n)}
                                            className={`transition-colors cursor-pointer ${isEditing
                                                ? 'bg-blue-900/30 hover:bg-blue-900/40'
                                                : 'hover:bg-slate-800/30'
                                                }`}
                                        >
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
                                            <td className="px-4 py-3">
                                                <div className="flex gap-1">
                                                    {(() => {
                                                        // Check if ping is enabled (either on node or inherited from group)
                                                        const pingEnabled = n.monitor_ping !== null ? n.monitor_ping : (group?.monitor_ping ?? true);
                                                        const snmpEnabled = n.monitor_snmp !== null ? n.monitor_snmp : (group?.monitor_snmp ?? false);

                                                        return (
                                                            <>
                                                                <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded border ${pingEnabled ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' : 'bg-slate-700/20 text-slate-600 border-slate-700/30'}`}>
                                                                    PING
                                                                </span>
                                                                <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded border ${snmpEnabled ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' : 'bg-slate-700/20 text-slate-600 border-slate-700/30'}`}>
                                                                    SNMP
                                                                </span>
                                                            </>
                                                        );
                                                    })()}
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    <button onClick={() => handleToggleNode(n)} className="bg-slate-700/50 hover:bg-slate-700 p-1 rounded transition-colors" title={n.enabled === false ? "Start Node" : "Pause Node"}>
                                                        {n.enabled === false ? <Play size={18} className="text-green-400" /> : <Pause size={18} className="text-orange-400" />}
                                                    </button>
                                                    <button onClick={() => handleDeleteNode(n.id)} className={`${deleteConfirm.type === 'node' && deleteConfirm.id === n.id ? 'bg-red-600 text-white px-2' : 'text-red-400 hover:text-red-300 p-1'} rounded transition-all flex items-center justify-center`}>
                                                        {deleteConfirm.type === 'node' && deleteConfirm.id === n.id ? <span className="text-xs font-bold">Confirm</span> : <Trash2 size={18} />}
                                                    </button>
                                                </div>
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

            {activeTab === 'metrics' && (
                <MetricsConfig nodes={nodes} groups={groups} />
            )}

            {activeTab === 'settings' && (
                <AppConfig />
            )}
        </div>
    );
};

export default Config;
