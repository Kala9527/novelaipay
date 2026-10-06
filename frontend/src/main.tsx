import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from './App'
import { PreferencesProvider } from './lib/preferences'
import './style.css'
import './studio.css'
import './features.css'
import './refresh.css'
import './welcome-carousel.css'
import './api-guide.css'

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><PreferencesProvider><BrowserRouter><App /></BrowserRouter></PreferencesProvider></React.StrictMode>)
