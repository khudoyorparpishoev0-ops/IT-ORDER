import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import './styles/fonts';

import './styles/tokens.css';
import './styles/base.css';
import { App } from './App';
import { ShellProvider } from './shell/ShellContext';

const container = document.getElementById('root');
if (!container) throw new Error('Не найден корневой элемент #root');

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <ShellProvider>
        <App />
      </ShellProvider>
    </BrowserRouter>
  </StrictMode>,
);
