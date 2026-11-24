import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Clock, Infinity as InfinityIcon, Timer } from 'lucide-react';
import { PAUSE_UNITS, MAX_PAUSE_VALUE, formatDuration } from '../pause';

const MENU_WIDTH = 256;

// Popover to pause a node: one of the configured periods, a custom duration, or until resumed.
// Uses fixed positioning so the scrolling table around the trigger cannot clip it.
const PauseMenu = ({ anchor, presets, onPause, onClose }) => {
    const ref = useRef(null);
    const [value, setValue] = useState(String(presets[0]?.value ?? 1));
    const [unit, setUnit] = useState(presets[0]?.unit ?? 'hours');

    // Place below the trigger, or above it when there is no room below
    useLayoutEffect(() => {
        const el = ref.current;
        const rect = anchor.getBoundingClientRect();
        const below = rect.bottom + 6;
        const top = below + el.offsetHeight > window.innerHeight - 8 ? Math.max(8, rect.top - el.offsetHeight - 6) : below;
        const left = Math.min(Math.max(8, rect.right - MENU_WIDTH), window.innerWidth - MENU_WIDTH - 8);
        el.style.top = `${top}px`;
        el.style.left = `${left}px`;
        el.style.visibility = 'visible';
    }, [anchor]);

    useEffect(() => {
        const onPointer = (e) => {
            if (ref.current?.contains(e.target) || anchor.contains(e.target)) return;
            onClose();
        };
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        const onMove = () => onClose();
        document.addEventListener('mousedown', onPointer);
        document.addEventListener('keydown', onKey);
        window.addEventListener('resize', onMove);
        window.addEventListener('scroll', onMove, true);
        return () => {
            document.removeEventListener('mousedown', onPointer);
            document.removeEventListener('keydown', onKey);
            window.removeEventListener('resize', onMove);
            window.removeEventListener('scroll', onMove, true);
        };
    }, [anchor, onClose]);

    const number = Number(value);
    const customValid = Number.isInteger(number) && number >= 1 && number <= MAX_PAUSE_VALUE[unit];

    const submitCustom = (e) => {
        e.preventDefault();
        if (customValid) onPause({ value: number, unit });
    };

    return (
        <div
            ref={ref}
            role="dialog"
            aria-label="Pause monitoring"
            onClick={(e) => e.stopPropagation()}
            style={{ top: 0, left: 0, width: MENU_WIDTH, visibility: 'hidden' }}
            className="fixed z-50 bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-2 text-left text-sm"
        >
            {presets.map(p => (
                <button
                    key={`${p.value}-${p.unit}`}
                    type="button"
                    onClick={() => onPause({ value: p.value, unit: p.unit })}
                    className="w-full flex items-center gap-2 px-2 py-2 rounded hover:bg-slate-700 text-slate-200"
                >
                    <Timer size={16} className="text-orange-400" />
                    Pause for {formatDuration(p.value, p.unit)}
                </button>
            ))}

            <form onSubmit={submitCustom} className={`px-2 py-2 ${presets.length ? 'border-t border-slate-700 mt-1' : ''}`}>
                <div className="text-xs text-slate-400 uppercase font-bold tracking-wider mb-1.5 flex items-center gap-1">
                    <Clock size={12} /> Custom
                </div>
                <div className="flex gap-1.5">
                    <input
                        type="number"
                        min="1"
                        max={MAX_PAUSE_VALUE[unit]}
                        step="1"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        aria-label="Pause duration"
                        className="w-16 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white focus:border-primary focus:outline-none"
                    />
                    <select
                        value={unit}
                        onChange={(e) => setUnit(e.target.value)}
                        aria-label="Pause unit"
                        className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white focus:border-primary focus:outline-none"
                    >
                        {PAUSE_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                    </select>
                    <button
                        type="submit"
                        disabled={!customValid}
                        className="px-2.5 py-1 rounded bg-orange-500/20 text-orange-300 hover:bg-orange-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        Pause
                    </button>
                </div>
                {!customValid && (
                    <p className="text-xs text-red-400 mt-1">Enter a whole number from 1 to {MAX_PAUSE_VALUE[unit]}.</p>
                )}
            </form>

            <button
                type="button"
                onClick={() => onPause({ indefinite: true })}
                className="w-full flex items-center gap-2 px-2 py-2 rounded hover:bg-slate-700 text-slate-300 border-t border-slate-700 mt-1"
            >
                <InfinityIcon size={16} className="text-slate-400" />
                Until resumed manually
            </button>
        </div>
    );
};

export default PauseMenu;
