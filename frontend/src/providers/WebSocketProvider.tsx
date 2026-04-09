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
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()
  const queryClient = useQueryClient()

  useEffect(() => {
    let reconnectAttempts = 0

    const connect = () => {
      // Derive WS URL from Vite API URL, fallback to localhost:8100
      const httpUrl = import.meta.env.VITE_API_URL || 'http://localhost:8100'
      const wsUrl = import.meta.env.VITE_WS_URL || `${httpUrl.replace('http', 'ws')}/ws`

      setStatus('connecting')
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('connected')
        reconnectAttempts = 0
        
        // Silent re-sync on connection
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
          
          // Route the incoming WSS payload directly into TanStack Query Cache and Toasts
          switch (payload.topic) {
            case 'dashboard_update':
              // Directly update dashboard query cache with new data
              queryClient.setQueryData(['dashboard'], payload.data)
              break
              
            case 'market_status_update':
              queryClient.setQueryData(['market-status'], payload.data)
              break
              
            case 'position_executed':
              // Invalidate relevant lists to force a refetch
              queryClient.invalidateQueries({ queryKey: ['dashboard'] })
              queryClient.invalidateQueries({ queryKey: ['positions'] })
              queryClient.invalidateQueries({ queryKey: ['ledger'] })
              
              // Fire Terminal Notification
              toast.success(`[EXEC_FILLED] ${payload.data?.symbol || 'UNKNOWN'}`, {
                description: `${payload.data?.side || 'TRADE'} | QTY: ${payload.data?.quantity || '--'} | @ $${payload.data?.price || '--'}`,
                duration: 5000,
              })
              break

            case 'worker_alert':
            case 'system_alert':
              // Generic alert handling from the backend
              const level = payload.data?.level || 'info'
              const title = `[${payload.topic.toUpperCase()}]`
              const desc = payload.data?.message || 'Unidentified system event.'
              
              if (level === 'error' || level === 'critical') {
                toast.error(title, { description: desc, duration: 8000 })
              } else if (level === 'warning') {
                toast.warning(title, { description: desc, duration: 5000 })
              } else {
                toast.info(title, { description: desc })
              }
              break

            default:
              // Generic invalidator for dynamic topics
              if (payload.action === 'invalidate' && payload.queryKey) {
                queryClient.invalidateQueries({ queryKey: payload.queryKey })
              }
              break
          }
        } catch (error) {
          console.error('[Forge_OS] Failed to parse WSS payload:', error)
        }
      }

      ws.onclose = () => {
        if (status === 'connected') {
          toast.error('[SYS_ERR] Uplink Severed', {
            description: 'Attempting to re-establish connection...',
          })
        }
        
        setStatus('disconnected')
        
        // Exponential backoff reconnect
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)
        reconnectAttempts++
        reconnectTimeoutRef.current = setTimeout(connect, timeout)
      }

      ws.onerror = () => {
        // ws.onclose will handle the reconnection
        ws.close()
      }
    }

    connect()

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (wsRef.current) {
        wsRef.current.onclose = null // Prevent reconnect loop on unmount
        wsRef.current.close()
      }
    }
  }, [queryClient]) // Note: removed `status` from deps to prevent infinite reconnect loops

  return (
    <WebSocketContext.Provider value={{ status, lastMessageTime }}>
      {children}
    </WebSocketContext.Provider>
  )
}