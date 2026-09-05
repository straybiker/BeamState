import React, { useEffect, useState, useRef, useCallback } from 'react';
import api from '../api';
import { FileText, ArrowDown, ArrowUp, Pause, Play, Wifi, WifiOff, Clock, PauseCircle, AlertTriangle } from 'lucide-react';

const StateTrace = () => {
    const [events, setEvents] = useState([]);
    const [pinToBottom, setPinToBottom] = useState(true);
    const [connected, setConnected] = useState(false);
    const [reliability, setReliability] = useState(null); // { day: {...}, month: {...}, nodes: [...] }
    const [showReliability, setShowReliability] = useState(true);

    const formatDuration = (s) => {
        if (!s) return '0s';
        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
        if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`;
        if (h) return `${h}h ${m}m`;
        return `${m}m ${s % 60}s`;
    };

    // Reliability table: availability per node over 24 h and 30 d
    useEffect(() => {
        const load = async () => {
            try {
                const [availRes, nodesRes] = await Promise.all([
                    api.get('/trace/availability?windows=24,720'),
                    api.get('/config/nodes')
                ]);
                const day = availRes.data.windows['24'] || {};
                const month = availRes.data.windows['720'] || {};
                const nodes = nodesRes.data
                    .map(n => ({ id: n.id, name: n.name, ip: n.ip, day: day[n.id], month: month[n.id] }))
                    .filter(n => n.month && n.month.availability !== null)
                    .sort((a, b) => (a.month.availability - b.month.availability) || (b.month.down_count - a.month.down_count));
                setReliability({ nodes });
            } catch (err) {
                console.error('Failed to load reliability stats:', err);
            }
        };
        Promise.resolve().then(load);
        const interval = setInterval(load, 60000);
        return () => clearInterval(interval);
    }, []);
    const containerRef = useRef(null);
    const eventSourceRef = useRef(null);

    // Scroll to bottom when pinned and new events arrive
    useEffect(() => {
        if (pinToBottom && containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [events, pinToBottom]);

    // Handle manual scroll - unpin if user scrolls up
    const handleScroll = useCallback(() => {
        if (!containerRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
        const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
        if (!isAtBottom && pinToBottom) {
            setPinToBottom(false);
        }
    }, [pinToBottom]);

    // Fetch initial events and setup SSE
    useEffect(() => {
        // Fetch recent events
        const fetchInitial = async () => {
            try {
                const res = await api.get('/trace/events?limit=200');
                if (res.data?.events) {
                    setEvents(res.data.events);
                }
            } catch (err) {
                console.error('Failed to fetch trace events:', err);
            }
        };
        fetchInitial();

        // Setup SSE connection
        const baseUrl = api.defaults.baseURL || '';
        const eventSource = new EventSource(`${baseUrl}/trace/stream`);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
            setConnected(true);
        };

        eventSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                setEvents(prev => [...prev.slice(-499), event]); // Keep last 500
            } catch (err) {
                console.error('Failed to parse SSE event:', err);
            }
        };

        eventSource.onerror = () => {
            setConnected(false);
        };

        return () => {
            eventSource.close();
        };
    }, []);

    // Status color and icon helpers
    const getStatusStyle = (status) => {
        switch (status) {
            case 'UP':
                return { color: 'text-green-400', bg: 'bg-green-500/20', icon: Wifi };
            case 'DOWN':
                return { color: 'text-red-400', bg: 'bg-red-500/20', icon: WifiOff };
            case 'PENDING':
                return { color: 'text-orange-400', bg: 'bg-orange-500/20', icon: Clock };
            case 'DEGRADED':
                return { color: 'text-amber-300', bg: 'bg-amber-500/20', icon: AlertTriangle };
            case 'PAUSED':
                return { color: 'text-slate-400', bg: 'bg-slate-500/20', icon: PauseCircle };
            default:
                return { color: 'text-slate-400', bg: 'bg-slate-500/20', icon: FileText };
        }
    };

    return (
        <div className="space-y-4 h-full flex flex-col">
            <header className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">State Trace</h2>
                    <p className="text-slate-400">Real-time node state changes</p>
                </div>
                <div className="flex items-center gap-4">
                    {/* Connection status */}
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${connected ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                        <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`}></span>
                        {connected ? 'Live' : 'Disconnected'}
                    </div>

                    {/* Pin to bottom toggle */}
                    <button
                        onClick={() => setPinToBottom(!pinToBottom)}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${pinToBottom ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'}`}
                    >
                        {pinToBottom ? <Play size={16} /> : <Pause size={16} />}
                        {pinToBottom ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
                    </button>

                    {/* Jump to bottom */}
                    {!pinToBottom && (
                        <button
                            onClick={() => {
                                setPinToBottom(true);
                                if (containerRef.current) {
                                    containerRef.current.scrollTop = containerRef.current.scrollHeight;
                                }
                            }}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
                        >
                            <ArrowDown size={16} />
                            Jump to Latest
                        </button>
                    )}
                </div>
            </header>

            {/* Reliability summary */}
            {reliability && reliability.nodes.length > 0 && (
                <div className="bg-surface border border-slate-700 rounded-xl overflow-hidden">
                    <button
                        onClick={() => setShowReliability(!showReliability)}
                        className="w-full flex items-center justify-between px-4 py-2 text-sm text-slate-300 hover:bg-slate-800/50"
                    >
                        <span className="font-semibold">Reliability (least available first)</span>
                        <span className="text-xs text-slate-500">{showReliability ? 'hide' : 'show'}</span>
                    </button>
                    {showReliability && (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm">
                                <thead className="bg-slate-800/50 text-slate-400 text-xs uppercase">
                                    <tr>
                                        <th className="px-4 py-2">Node</th>
                                        <th className="px-4 py-2 text-right">24 h</th>
                                        <th className="px-4 py-2 text-right">30 d</th>
                                        <th className="px-4 py-2 text-right">DOWN events (30 d)</th>
                                        <th className="px-4 py-2 text-right">Downtime (30 d)</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-800">
                                    {reliability.nodes.slice(0, 10).map(n => {
                                        const color = (v) => v === null || v === undefined ? 'text-slate-500' : v >= 99.9 ? 'text-green-400' : v >= 99 ? 'text-amber-300' : 'text-red-400';
                                        return (
                                            <tr key={n.id} className="hover:bg-slate-800/30">
                                                <td className="px-4 py-2 text-slate-200">{n.name} <span className="text-slate-500 text-xs">({n.ip})</span></td>
                                                <td className={`px-4 py-2 text-right font-mono ${color(n.day?.availability)}`}>{n.day?.availability ?? '-'}%</td>
                                                <td className={`px-4 py-2 text-right font-mono ${color(n.month.availability)}`}>{n.month.availability}%</td>
                                                <td className="px-4 py-2 text-right font-mono text-slate-300">{n.month.down_count}</td>
                                                <td className="px-4 py-2 text-right font-mono text-slate-300">{formatDuration(n.month.downtime_seconds)}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                            {reliability.nodes.length > 10 && (
                                <div className="px-4 py-2 text-xs text-slate-500">Showing the 10 least available of {reliability.nodes.length} nodes.</div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Event count */}
            <div className="text-sm text-slate-500">
                {events.length} events in buffer
            </div>

            {/* Event log container */}
            <div
                ref={containerRef}
                onScroll={handleScroll}
                className="flex-1 bg-slate-900/50 border border-slate-700 rounded-xl overflow-y-auto font-mono text-sm"
                style={{ minHeight: '400px', maxHeight: 'calc(100vh - 280px)' }}
            >
                {events.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-slate-500">
                        <div className="text-center">
                            <FileText size={48} className="mx-auto mb-4 opacity-30" />
                            <p>No state changes recorded yet.</p>
                            <p className="text-xs mt-2">Events will appear here as nodes change state.</p>
                        </div>
                    </div>
                ) : (
                    <div className="divide-y divide-slate-800">
                        {events.map((event, idx) => {
                            const oldStyle = getStatusStyle(event.old_status);
                            const newStyle = getStatusStyle(event.new_status);
                            const OldIcon = oldStyle.icon;
                            const NewIcon = newStyle.icon;

                            return (
                                <div key={`${event.timestamp}-${idx}`} className="px-4 py-3 hover:bg-slate-800/50 transition-colors">
                                    <div className="flex items-center gap-4">
                                        {/* Timestamp */}
                                        <span className="text-slate-500 text-xs w-40 flex-shrink-0">
                                            {event.timestamp_iso}
                                        </span>

                                        {/* Node info */}
                                        <div className="flex-1 min-w-0">
                                            <span className="text-slate-200 font-medium">{event.node_name}</span>
                                            <span className="text-slate-500 ml-2">({event.ip})</span>
                                            <span className="text-slate-600 ml-2 text-xs">[{event.group_name}]</span>
                                        </div>

                                        {/* Status transition */}
                                        <div className="flex items-center gap-2 flex-shrink-0">
                                            <span className={`flex items-center gap-1 px-2 py-0.5 rounded ${oldStyle.bg} ${oldStyle.color}`}>
                                                <OldIcon size={12} />
                                                {event.old_status}
                                            </span>
                                            <ArrowDown size={14} className="text-slate-500 rotate-[-90deg]" />
                                            <span className={`flex items-center gap-1 px-2 py-0.5 rounded ${newStyle.bg} ${newStyle.color}`}>
                                                <NewIcon size={12} />
                                                {event.new_status}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Reason */}
                                    <div className="mt-1 ml-44 text-xs text-slate-500 italic">
                                        {event.reason}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
};

export default StateTrace;
