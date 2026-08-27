import { RunClient, runClient } from './api/runClient';
import { ChatWorkspace } from './components/chat/ChatWorkspace';

interface AppProps {
  client?: RunClient;
}

export function App({ client = runClient }: AppProps) {
  return (
    <main className="circuit-grid min-h-screen w-full">
      <ChatWorkspace client={client} />
    </main>);

}
