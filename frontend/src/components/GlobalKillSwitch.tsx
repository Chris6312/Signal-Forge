import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertOctagon, AlertTriangle, X, ShieldAlert } from 'lucide-react'
import { haltTrading } from '@/api/endpoints'
import clsx from 'clsx'

export default function GlobalKillSwitch() {
  const [isOpen, setIsOpen] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [adminToken, setAdminToken] = useState('')
  const queryClient = useQueryClient()

  const haltMutation = useMutation({
    mutationFn: () => haltTrading(adminToken),
    onSuccess: () => {
      setIsOpen(false)
      setConfirmText('')
      setAdminToken('')
      // Force dashboard and runtime queries to instantly fetch the new "halted" state
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['runtime'] })
      queryClient.invalidateQueries({ queryKey: ['market-status'] })
    },
  })

  const isReady = confirmText === 'HALT' && adminToken.trim().length > 0

  return (
    <>
      {/* The Hardware-Style Button */}
      <button
        onClick={() => setIsOpen(true)}
        className="relative overflow-hidden bg-system-offline hover:bg-red-600 text-white font-bold py-1.5 px-3 md:px-4 rounded border border-red-400/50 shadow-[0_0_15px_-3px_rgba(239,68,68,0.4)] hover:shadow-[0_0_20px_-3px_rgba(239,68,68,0.6)] transition-all flex items-center gap-2 text-sm uppercase tracking-wider group shrink-0"
      >
        {/* CSS Hazard Stripes */}
        <div className="absolute inset-0 opacity-20 bg-[repeating-linear-gradient(45deg,transparent,transparent_8px,#000_8px,#000_16px)] pointer-events-none group-hover:opacity-30 transition-opacity"></div>
        <AlertOctagon size={16} className="relative z-10 animate-pulse" />
        <span className="relative z-10 mono text-xs mt-0.5 hidden xl:inline">INITIATE_GLOBAL_HALT (soft)</span>
        <span className="relative z-10 mono text-xs mt-0.5 xl:hidden">HALT</span>
      </button>

      {/* The Confirmation Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-[#0b0c13] border border-system-offline shadow-[0_0_30px_-5px_rgba(239,68,68,0.3)] rounded-xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="bg-system-offline/10 border-b border-system-offline/30 px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3 text-system-offline">
                <ShieldAlert size={20} className="animate-pulse" />
                <h2 className="font-mono font-bold tracking-widest uppercase text-sm">Critical Override</h2>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-500 hover:text-white transition-colors"
                disabled={haltMutation.isPending}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 space-y-4">
              <div className="bg-system-offline/10 text-red-300 p-4 rounded-lg border border-system-offline/20 flex gap-3 text-sm">
                <AlertTriangle size={18} className="shrink-0 mt-0.5" />
                <p>
                  This control sets the system-level trading flag to <strong>disabled</strong>. Workers will observe the flag and stop initiating new trades. This is a soft halt: it does not cancel existing open positions or pending orders and does not override exit policies.
                </p>
              </div>

              <div className="space-y-3 pt-2">
                <div>
                  <label className="block text-xs font-mono text-gray-400 mb-1.5 uppercase">Admin Token</label>
                  <input
                    type="password"
                    value={adminToken}
                    onChange={(e) => setAdminToken(e.target.value)}
                    className="w-full bg-[#12141f] border border-surface-border rounded py-2 px-3 text-white font-mono text-sm focus:outline-none focus:border-system-offline focus:ring-1 focus:ring-system-offline transition-all"
                    placeholder="Enter x-admin-token"
                    autoComplete="off"
                    disabled={haltMutation.isPending}
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-gray-400 mb-1.5 uppercase">
                    Type <span className="text-system-offline font-bold">HALT</span> to confirm
                  </label>
                  <input
                    type="text"
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    className="w-full bg-[#12141f] border border-surface-border rounded py-2 px-3 text-white font-mono text-sm focus:outline-none focus:border-system-offline focus:ring-1 focus:ring-system-offline transition-all uppercase"
                    placeholder="HALT"
                    autoComplete="off"
                    disabled={haltMutation.isPending}
                  />
                </div>
              </div>

              {/* Error Message */}
              {haltMutation.isError && (
                <div className="text-system-offline text-xs font-mono bg-red-500/10 p-2 rounded">
                  [ERR] {(haltMutation.error as any)?.response?.data?.detail || haltMutation.error.message}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="bg-[#12141f] border-t border-surface-border px-5 py-4 flex justify-end gap-3">
              <button
                onClick={() => setIsOpen(false)}
                className="btn-ghost"
                disabled={haltMutation.isPending}
              >
                CANCEL
              </button>
              <button
                onClick={() => haltMutation.mutate()}
                disabled={!isReady || haltMutation.isPending}
                className={clsx(
                  "py-2 px-6 rounded text-sm font-bold tracking-wider uppercase font-mono transition-all",
                  isReady 
                    ? "bg-system-offline hover:bg-red-600 text-white shadow-[0_0_15px_-3px_rgba(239,68,68,0.5)]" 
                    : "bg-surface-border text-gray-500 cursor-not-allowed"
                )}
              >
                {haltMutation.isPending ? 'EXECUTING...' : 'CONFIRM HALT'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}