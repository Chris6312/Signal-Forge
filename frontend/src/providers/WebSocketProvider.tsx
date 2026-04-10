/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

interface WebSocketContextValue {
  status: ConnectionStatus
  lastMessageTime: number | null
}

const WebSocketContext = createContext<WebSocketContextValue>({
  status: 'disconnected',
  lastMessageTime: null,
})

export function useWebSocket() {
  return useContext(WebSocketContext)
}

export default function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [lastMessageTime, setLastMessageTime] = useState<number | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const connectedRef = useRef<boolean>(false)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>()
  const queryClient = useQueryClient()

  useEffect(() => {
    let reconnectAttempts = 0

    const connect = () => {
      const httpUrl = import.meta.env.VITE_API_URL || 'http://localhost:8100'
      const wsUrl = import.meta.env.VITE_WS_URL || `${httpUrl.replace('http', 'ws')}/ws`

      setStatus('connecting')
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        connectedRef.current = true
        reconnectAttempts = 0

        // Ensure critical queries are refreshed after reconnect
        queryClient.invalidateQueries({ queryKey: ['dashboard'] })
        queryClient.invalidateQueries({ queryKey: ['market-status'] })

        toast.success('[SYS_MSG] Uplink Established', {
          description: 'Telemetry stream is active.',
        })
      }

      ws.onmessage = (event) => {
        setLastMessageTime(Date.now())
        try {
          const payload = JSON.parse(event.data)

          // Primary topic routing
          switch (payload.topic) {
            case 'dashboard_update':
              queryClient.setQueryData(['dashboard'], payload.data)
              break

            case 'market_status_update':
              queryClient.setQueryData(['market-status'], payload.data)
              break

            case 'position_executed':
              // Keep dashboard and positions fresh
              queryClient.invalidateQueries({ queryKey: ['dashboard'] })
              queryClient.invalidateQueries({ queryKey: ['positions'] })
              // Fix: invalidate both ledger accounts and entries (previously used incorrect key)
              queryClient.invalidateQueries({ queryKey: ['ledger-accounts'] })
              queryClient.invalidateQueries({ queryKey: ['ledger-entries'] })

              toast.success(`[EXEC_FILLED] ${payload.data?.symbol || 'UNKNOWN'}`, {
                description: `${payload.data?.side || 'TRADE'} | QTY: ${payload.data?.quantity || '--'} | @ $${payload.data?.price || '--'}`,
                duration: 5000,
              })
              break

            case 'trades_update':
              // Trades list changed: invalidate trade history and summaries
              queryClient.invalidateQueries({ queryKey: ['trades'] })
              queryClient.invalidateQueries({ queryKey: ['trade-summary'] })
              break

            case 'audit_update':
              queryClient.invalidateQueries({ queryKey: ['audit'] })
              break

            case 'monitoring_update':
              queryClient.invalidateQueries({ queryKey: ['monitoring'] })
              break

            case 'watchlist_update':
              queryClient.invalidateQueries({ queryKey: ['watchlist'] })
              break

            case 'runtime_update':
              // Replace runtime state cache directly
              queryClient.setQueryData(['runtime'], payload.data)
              break

            case 'ledger_accounts_update':
              if (payload.data != null) {
                queryClient.setQueryData(['ledger-accounts'], payload.data)
              } else {
                queryClient.invalidateQueries({ queryKey: ['ledger-accounts'] })
              }
              break

            case 'ledger_entries_update':
              if (payload.data != null) {
                queryClient.setQueryData(['ledger-entries'], payload.data)
              } else {
                queryClient.invalidateQueries({ queryKey: ['ledger-entries'] })
              }
              break

            // Generic topics and invalidation support
            default: {
              // Support both legacy root-level invalidation and nested data invalidation
              const action = payload.action || payload.data?.action
              const queryKey = payload.queryKey || payload.data?.queryKey
              if (action === 'invalidate' && queryKey) {
                try {
                  queryClient.invalidateQueries({ queryKey })
                } catch (err) {
                  console.error('[WS] Invalidation failed', err)
                }
              }
            }
          }
        } catch (error) {
          console.error('[Forge_OS] Failed to parse WSS payload:', error)
        }
      }

      ws.onclose = () => {
        if (connectedRef.current) {
          toast.error('[SYS_ERR] Uplink Severed', {
            description: 'Attempting to re-establish connection...',
          })
        }

        connectedRef.current = false
        setStatus('disconnected')

        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)
        reconnectAttempts++
        reconnectTimeoutRef.current = setTimeout(connect, timeout)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [queryClient])

  return (
    <WebSocketContext.Provider value={{ status, lastMessageTime }}>
      {children}
    </WebSocketContext.Provider>
  )
}
