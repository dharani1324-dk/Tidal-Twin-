/**
 * Phase 9 — route/surface error boundary.
 *
 * A failure in one surface (Copilot, TIDE, Cesium, a chart) must never crash
 * the whole Digital Twin. Each route is wrapped in its own boundary so the
 * navigation, status bar and remaining surfaces keep working.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import './ErrorBoundary.css'

interface Props {
  label: string
  children: ReactNode
  onReset?: () => void
}

interface State {
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Useful for diagnosis; never includes user secrets.
    console.error(`[ErrorBoundary:${this.props.label}]`, error, info.componentStack)
  }

  private reset = () => {
    this.setState({ error: null })
    this.props.onReset?.()
  }

  render() {
    if (this.state.error) {
      return (
        <div className="err-boundary" role="alert">
          <span className="err-boundary-icon" aria-hidden>
            <AlertTriangle size={22} />
          </span>
          <div className="err-boundary-body">
            <b>{this.props.label} is temporarily unavailable.</b>
            <p>
              This surface failed to render. The rest of the Digital Twin is unaffected. No values are
              fabricated while it is down.
            </p>
            <code className="err-boundary-msg">{this.state.error.message}</code>
          </div>
          <button className="err-boundary-retry" onClick={this.reset}>
            Retry {this.props.label}
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
