import React from 'react';
import ReactDOM from 'react-dom/client';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MotionConfig} from 'motion/react';
import App from './App';
import '@fontsource-variable/inter';
import './styles.css';
import './workflow-detail.css';

const queryClient = new QueryClient({defaultOptions:{queries:{refetchOnWindowFocus:false, retry:1}}});
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}>
  <MotionConfig reducedMotion="user"><App/></MotionConfig>
</QueryClientProvider></React.StrictMode>);
