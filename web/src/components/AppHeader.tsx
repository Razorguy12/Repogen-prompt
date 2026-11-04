import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'
import { useAuth } from '../context/AuthContext'

interface AppHeaderProps {
  variant?: 'default' | 'landing'
}

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 sm:gap-3 no-underline shrink-0">
      <img src={logoUrl} alt="" className="w-8 h-8 sm:w-9 sm:h-9 shrink-0" />
      <span className="text-lg sm:text-xl font-bold text-primary-dark tracking-tight">repogen</span>
    </Link>
  )
}

export function AppHeader({ variant = 'default' }: AppHeaderProps) {
  const { token, name, isAdmin, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  if (variant === 'landing') {
    return (
      <header className="relative w-full px-4 sm:px-6 py-3.5 bg-white/70 backdrop-blur-md border-b border-white/50 flex justify-between items-center">
        <Logo />
        <nav className="flex items-center gap-2 sm:gap-3">
          <Link to="/login" className="btn btn-secondary text-xs sm:text-sm py-1.5 sm:py-2 px-3 sm:px-4">
            Sign In
          </Link>
          <Link to="/login" className="btn btn-primary text-xs sm:text-sm py-1.5 sm:py-2 px-3 sm:px-4">
            Get Started
          </Link>
        </nav>
      </header>
    )
  }

  return (
    <header className="relative w-full px-4 sm:px-6 py-3 bg-white/75 backdrop-blur-md border-b border-slate-200/60">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-2">
        <Logo />

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center gap-2.5">
          {token && (
            <>
              <Link to={location.pathname === '/dashboard' ? '/generate' : '/dashboard'} className="btn btn-secondary text-xs sm:text-sm py-1.5 px-3.5">
                {location.pathname === '/dashboard' ? 'Back to Chat' : 'Dashboard'}
              </Link>
              <Link to="/generate" className="btn btn-primary text-xs sm:text-sm py-1.5 px-3.5">
                + New Report
              </Link>
              {isAdmin && (
                <div className="flex items-center gap-1">
                  <Link to="/admin" className="btn btn-secondary text-xs sm:text-sm py-1.5 px-3">Admin</Link>
                  <Link to="/admin/audit-logs" className="btn btn-secondary text-xs sm:text-sm py-1.5 px-3">Audit Logs</Link>
                </div>
              )}
              <span className="text-xs font-semibold text-slate-700 bg-slate-100 px-2.5 py-1 rounded-full">
                {name}
              </span>
              <button onClick={handleLogout} className="btn btn-secondary text-xs sm:text-sm py-1.5 px-3">
                Logout
              </button>
            </>
          )}
          {!token && (
            <Link to="/login" className="btn btn-primary text-xs sm:text-sm py-1.5 px-4">
              Login
            </Link>
          )}
        </nav>

        {/* Mobile Hamburger Button */}
        <div className="flex md:hidden items-center gap-2">
          {token && (
            <Link to="/generate" className="btn btn-primary text-xs py-1.5 px-2.5 font-semibold">
              + New
            </Link>
          )}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 text-sm cursor-pointer"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? '✕' : '☰'}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden pt-3 pb-2 border-t border-slate-200/60 mt-2 space-y-2 animate-fadeIn">
          {token && (
            <>
              <div className="px-2 py-1 text-xs text-slate-500 font-medium">
                Signed in as: <strong className="text-slate-800">{name}</strong>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Link
                  to={location.pathname === '/dashboard' ? '/generate' : '/dashboard'}
                  onClick={() => setMobileMenuOpen(false)}
                  className="btn btn-secondary text-xs py-2 px-3 text-center"
                >
                  {location.pathname === '/dashboard' ? '← Back to Chat' : '📊 Dashboard'}
                </Link>
                <Link
                  to="/generate"
                  onClick={() => setMobileMenuOpen(false)}
                  className="btn btn-primary text-xs py-2 px-3 text-center"
                >
                  + New Report
                </Link>
                {isAdmin && (
                  <>
                    <Link to="/admin" onClick={() => setMobileMenuOpen(false)} className="btn btn-secondary text-xs py-2 px-3 text-center">Admin Panel</Link>
                    <Link to="/admin/audit-logs" onClick={() => setMobileMenuOpen(false)} className="btn btn-secondary text-xs py-2 px-3 text-center">Audit Logs</Link>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setMobileMenuOpen(false)
                    handleLogout()
                  }}
                  className="btn btn-secondary text-xs py-2 px-3 text-rose-600 border-rose-200 col-span-2 text-center"
                >
                  🚪 Logout
                </button>
              </div>
            </>
          )}
          {!token && (
            <Link
              to="/login"
              onClick={() => setMobileMenuOpen(false)}
              className="btn btn-primary text-xs py-2 w-full text-center block"
            >
              Login
            </Link>
          )}
        </div>
      )}
    </header>
  )
}
