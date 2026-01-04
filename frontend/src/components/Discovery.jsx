
import React, { useState, useEffect } from 'react';
import api from '../api';
import { Network, Database, Server, Smartphone, Monitor } from 'lucide-react';
import toast from 'react-hot-toast';

const Discovery = () => {
    const [cidr, setCidr] = useState('192.168.1.0/24');
    const [scanning, setScanning] = useState(false);
    const [results, setResults] = useState([]);
    const [selectedIPs, setSelectedIPs] = useState(new Set());
    const [groups, setGroups] = useState([]);
    const [selectedGroup, setSelectedGroup] = useState('');
    const [importing, setImporting] = useState(false);

    // New states
    const [protocols, setProtocols] = useState({ icmp: true, snmp: true });
    const [stats, setStats] = useState({ progress: 0, total: 0, scanned: 0, icmp_found: 0, snmp_found: 0 });
    const [pollInterval, setPollInterval] = useState(null);

    useEffect(() => {
        fetchGroups();
        checkStatus();
        return () => stopPolling();
    }, []);

    const fetchGroups = () => {
        api.get('/config/groups')
            .then(res => {
                setGroups(res.data);
                if (res.data.length > 0) {
                    setSelectedGroup(res.data[0].id);
                }
            })
            .catch(err => toast.error("Failed to load groups"));
    };

    const checkStatus = async () => {
        try {
            const res = await api.get('/discovery/status');
            const data = res.data;

            // Restore stats and results
            if (data.results && data.results.length > 0) {
                setResults(data.results);
            }

            setStats({
                progress: data.progress,
                total: data.total,
                ...data.stats
            });

            // If running, resume polling and set scanning state
            if (data.running) {
                setScanning(true);
                startPolling();
            }
        } catch (e) {
            console.error("Failed to check status", e);
        }
    };

    const startPolling = () => {
        stopPolling();
        const interval = setInterval(async () => {
            try {
                const res = await api.get('/discovery/status');
                const data = res.data;

                // Always update stats
                setStats({
                    progress: data.progress,
                    total: data.total,
                    ...data.stats
                });

                // Update results if changed (basic length check or just overwrite)
                if (data.results) {
                    setResults(data.results);
                }

                if (!data.running && scanning) {
                    setScanning(false);
                    stopPolling();
                    toast.success(`Scan complete. Found ${data.results.length} devices.`);
                }
            } catch (e) {
                console.error("Poll failed", e);
            }
        }, 1000);
        setPollInterval(interval);
    };

    const stopPolling = () => {
        if (pollInterval) {
            clearInterval(pollInterval);
            setPollInterval(null);
        }
    };

    const handleScan = async () => {
        if (!cidr) {
            toast.error("Please enter a valid CIDR");
            return;
        }
        if (!protocols.icmp && !protocols.snmp) {
            toast.error("Select at least one protocol");
            return;
        }

        setScanning(true);
        setResults([]);
        setSelectedIPs(new Set());
        setStats({ progress: 0, total: 0, scanned: 0, icmp_found: 0, snmp_found: 0 });

        startPolling();

        try {
            // Protocol list for API
            const protocolList = [];
            if (protocols.icmp) protocolList.push('icmp');
            if (protocols.snmp) protocolList.push('snmp');

            const res = await api.post('/discovery/scan', {
                cidr,
                protocols: protocolList
            });
            setResults(res.data);
            if (res.data.length === 0) {
                toast("No devices found", { icon: '🔍' });
            } else {
                toast.success(`Found ${res.data.length} devices`);
            }
        } catch (error) {
            console.error(error);
            toast.error(error.response?.data?.detail || "Scan failed");
        } finally {
            setScanning(false);
            stopPolling();
            // Final fetch for 100% stats? Or just let it settle.
        }
    };

    const toggleSelection = (ip) => {
        const newSet = new Set(selectedIPs);
        if (newSet.has(ip)) {
            newSet.delete(ip);
        } else {
            newSet.add(ip);
        }
        setSelectedIPs(newSet);
    };

    const selectAll = () => {
        if (selectedIPs.size === results.length) {
            setSelectedIPs(new Set());
        } else {
            setSelectedIPs(new Set(results.map(r => r.ip)));
        }
    };

    const handleImport = async () => {
        if (selectedIPs.size === 0) {
            toast.error("No devices selected");
            return;
        }
        if (!selectedGroup) {
            toast.error("Please select a target group");
            return;
        }

        setImporting(true);
        const hostsToImport = results.filter(r => selectedIPs.has(r.ip));

        try {
            // Protocol list for API
            const protocolList = [];
            if (protocols.icmp) protocolList.push('icmp');
            if (protocols.snmp) protocolList.push('snmp');

            const res = await api.post('/discovery/import', {
                hosts: hostsToImport,
                target_group_id: selectedGroup,
                protocols: protocolList
            });
            const { imported, updated, skipped } = res.data;
            const parts = [];
            if (imported > 0) parts.push(`${imported} added`);
            if (updated > 0) parts.push(`${updated} updated`);
            if (skipped > 0) parts.push(`${skipped} skipped`);
            toast.success(parts.join(', ') || 'No changes');
            setSelectedIPs(new Set());
        } catch (error) {
            console.error(error);
            toast.error(error.response?.data?.detail || "Import failed");
        } finally {
            setImporting(false);
        }
    };

    // Calculate percentage
    const progressPercent = stats.total > 0 ? Math.min(100, Math.round((stats.progress / stats.total) * 100)) : 0;

    return (
        <div className="space-y-6">
            <div className="bg-slate-800 p-6 rounded-lg shadow-lg border border-slate-700">
                <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                    <Network size={24} className="text-blue-400" />
                    Network Discovery
                </h2>

                <div className="flex flex-col md:flex-row gap-6 items-end">
                    <div className="flex-1 w-full space-y-4">
                        <div>
                            <label className="block text-sm text-slate-400 mb-1">Target Subnet (CIDR)</label>
                            <input
                                type="text"
                                value={cidr}
                                onChange={e => setCidr(e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 focus:ring-2 focus:ring-blue-500 outline-none"
                                placeholder="e.g. 192.168.1.0/24"
                            />
                        </div>

                        <div className="flex gap-6">
                            <label className="flex items-center gap-2 cursor-pointer hover:text-white transition-colors">
                                <input
                                    type="checkbox"
                                    checked={protocols.icmp}
                                    onChange={e => setProtocols({ ...protocols, icmp: e.target.checked })}
                                    className="rounded bg-slate-700 border-slate-600 text-blue-500 focus:ring-blue-500"
                                />
                                <span className={protocols.icmp ? 'text-slate-200' : 'text-slate-500'}>ICMP (Ping)</span>
                            </label>

                            <label className="flex items-center gap-2 cursor-pointer hover:text-white transition-colors">
                                <input
                                    type="checkbox"
                                    checked={protocols.snmp}
                                    onChange={e => setProtocols({ ...protocols, snmp: e.target.checked })}
                                    className="rounded bg-slate-700 border-slate-600 text-blue-500 focus:ring-blue-500"
                                />
                                <span className={protocols.snmp ? 'text-slate-200' : 'text-slate-500'}>SNMP (Details)</span>
                            </label>
                        </div>
                    </div>

                    <button
                        onClick={handleScan}
                        disabled={scanning}
                        className={`px-6 py-2 rounded font-medium flex items-center gap-2 h-10 ${scanning ? 'bg-slate-700 cursor-not-allowed text-slate-400' : 'bg-blue-600 hover:bg-blue-500 text-white'
                            }`}
                    >
                        {scanning ? 'Scanning...' : 'Start Scan'}
                    </button>
                </div>

                {/* Progress Bar Area */}
                {(scanning || stats.progress > 0) && (
                    <div className="mt-6 pt-4 border-t border-slate-700/50">
                        <div className="flex justify-between text-sm text-slate-400 mb-2">
                            <span>Progress: {progressPercent}%</span>
                            <span>{stats.scanned} / {stats.total} Targets</span>
                        </div>
                        <div className="w-full bg-slate-700 rounded-full h-2.5 overflow-hidden">
                            <div
                                className="bg-blue-500 h-2.5 rounded-full transition-all duration-300"
                                style={{ width: `${progressPercent}%` }}
                            ></div>
                        </div>

                        <div className="flex gap-6 mt-4 text-sm justify-center">
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-blue-400"></div>
                                <span className="text-slate-300">Scanned: {stats.scanned}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-green-400"></div>
                                <span className="text-slate-300">Ping Responders: {stats.icmp_found}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-purple-400"></div>
                                <span className="text-slate-300">SNMP Devices: {stats.snmp_found}</span>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {results.length > 0 && (
                <div className="bg-slate-800 p-6 rounded-lg shadow-lg border border-slate-700">
                    <div className="flex justify-between items-center mb-4">
                        <h3 className="text-lg font-semibold">Scan Results ({results.length})</h3>

                        <div className="flex gap-4 items-center">
                            <select
                                value={selectedGroup}
                                onChange={e => setSelectedGroup(e.target.value)}
                                className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm outline-none"
                            >
                                <option value="" disabled>Select Target Group</option>
                                {groups.map(g => (
                                    <option key={g.id} value={g.id}>{g.name}</option>
                                ))}
                            </select>

                            <button
                                onClick={handleImport}
                                disabled={importing || selectedIPs.size === 0}
                                className={`px-4 py-2 rounded text-sm font-medium ${importing || selectedIPs.size === 0
                                    ? 'bg-slate-700 text-slate-400 cursor-not-allowed'
                                    : 'bg-green-600 hover:bg-green-500 text-white'
                                    }`}
                            >
                                {importing ? 'Importing...' : `Import Selected (${selectedIPs.size})`}
                            </button>
                        </div>
                    </div>

                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="border-b border-slate-700 text-slate-400 text-sm uppercas">
                                    <th className="p-3 w-10">
                                        <input
                                            type="checkbox"
                                            onChange={selectAll}
                                            checked={results.length > 0 && selectedIPs.size === results.length}
                                            className="rounded bg-slate-700 border-slate-600"
                                        />
                                    </th>
                                    <th className="p-3">IP Address</th>
                                    <th className="p-3">Hostname</th>
                                    <th className="p-3">Type</th>
                                    <th className="p-3">Latency</th>
                                    <th className="p-3">Protocols</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700/50">
                                {results.map(device => (
                                    <tr key={device.ip} className="hover:bg-slate-700/30 transition-colors">
                                        <td className="p-3">
                                            <input
                                                type="checkbox"
                                                checked={selectedIPs.has(device.ip)}
                                                onChange={() => toggleSelection(device.ip)}
                                                className="rounded bg-slate-700 border-slate-600"
                                            />
                                        </td>
                                        <td className="p-3 font-mono text-blue-400">{device.ip}</td>
                                        <td className="p-3 text-slate-300">{device.hostname || '-'}</td>
                                        <td className="p-3">
                                            <span className="flex items-center gap-2">
                                                {getIconForType(device.type)}
                                                {device.vendor} {device.type}
                                            </span>
                                        </td>
                                        <td className="p-3 text-green-400 font-mono text-sm">
                                            {typeof device.latency === 'number' ? `${device.latency.toFixed(1)} ms` : '-'}
                                        </td>
                                        <td className="p-3">
                                            <div className="flex gap-2">
                                                {typeof device.latency === 'number' && (
                                                    <span className="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded text-xs border border-blue-500/20">ICMP</span>
                                                )}
                                                {device.snmp_enabled && (
                                                    <span className="bg-green-500/10 text-green-400 px-2 py-0.5 rounded text-xs border border-green-500/20">SNMP</span>
                                                )}
                                                {typeof device.latency !== 'number' && !device.snmp_enabled && (
                                                    <span className="text-slate-500 text-xs">-</span>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};

const getIconForType = (type) => {
    switch (type) {
        case 'Server': return <Server size={16} className="text-purple-400" />;
        case 'Switch': return <Network size={16} className="text-blue-400" />;
        case 'Access Point': return <Monitor size={16} className="text-orange-400" />; // Wifi icon would be better but lucide Monitor is fine
        default: return <Database size={16} className="text-slate-400" />;
    }
}

export default Discovery;
