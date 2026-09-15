import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// ditto themes on a .dark class rather than the prefers-color-scheme query,
// so the console keeps that contract and follows the device for now. When a
// theme toggle is wanted, it sets this class and nothing else changes.
const media = window.matchMedia('(prefers-color-scheme: dark)')
const applyTheme = (isDark) =>
  document.documentElement.classList.toggle('dark', isDark)

applyTheme(media.matches)
media.addEventListener('change', (event) => applyTheme(event.matches))

const app = mount(App, {
  target: document.getElementById('app'),
})

export default app
