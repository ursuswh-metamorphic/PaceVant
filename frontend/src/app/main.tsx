import React from 'react';
import ReactDOM from 'react-dom/client';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MotionConfig} from 'motion/react';
import App from './App';
import './styles.css';
import './workflow-detail.css';

// Track input modality so script-moved focus (Radix roving tabs) only shows a ring for keyboard users.
const root = document.documentElement;
window.addEventListener('keydown', event => {
  if (['Tab', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'Enter', ' '].includes(event.key)) root.dataset.input = 'keyboard';
}, true);
window.addEventListener('pointerdown', () => { root.dataset.input = 'pointer'; }, true);

const queryClient = new QueryClient({defaultOptions:{queries:{refetchOnWindowFocus:false, retry:1}}});
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={queryClient}>
  <MotionConfig reducedMotion="user"><App/></MotionConfig>
</QueryClientProvider></React.StrictMode>);
