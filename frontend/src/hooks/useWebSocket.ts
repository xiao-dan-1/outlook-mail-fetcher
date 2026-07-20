import { useCallback, useEffect, useRef, useState } from 'react';

interface FetchProgress {
  status: 'started' | 'progress' | 'completed' | 'error' | 'account_failed';
  total: number;
  completed: number;
  failed: number;
  account?: string;
  messages?: number;
  error?: string;
}

interface UseWebSocketFetchOptions {
  onProgress?: (progress: FetchProgress) => void;
  onComplete?: (result: any) => void;
  onError?: (error: string) => void;
}

export function useWebSocketFetch(options: UseWebSocketFetchOptions = {}) {
  const { onProgress, onComplete, onError } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isFetching, setIsFetching] = useState(false);

  const connect = useCallback(() => {
    const ws = new WebSocket(`ws://${window.location.host}/ws/fetch`);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'progress') {
        onProgress?.(data);
        
        if (data.status === 'completed') {
          setIsFetching(false);
          onComplete?.(data);
        } else if (data.status === 'error') {
          setIsFetching(false);
          onError?.(data.error || 'Unknown error');
        }
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsFetching(false);
    };

    ws.onerror = () => {
      setIsConnected(false);
      setIsFetching(false);
      onError?.('WebSocket connection error');
    };
  }, [onProgress, onComplete, onError]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsFetching(false);
  }, []);

  const startFetch = useCallback((payload: any) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      onError?.('WebSocket not connected');
      return;
    }
    
    setIsFetching(true);
    wsRef.current.send(JSON.stringify(payload));
  }, [onError]);

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected,
    isFetching,
    startFetch,
    disconnect,
  };
}
