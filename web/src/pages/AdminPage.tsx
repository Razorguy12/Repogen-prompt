import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { AppHeader } from '../components/AppHeader'
import { ReportCard } from '../components/ReportCard'
import { useAuth } from '../context/AuthContext'
import { getUsers, createUser, getUserReports, getReports, updateUserPassword, deleteDoctor } from '../api/reports'
import type { AdminUser } from '../types'
import { ApiError } from '../api/client'

export default function AdminPage() {
  const { name } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'users' | 'my-reports'>('users')
  const [userSearch, setUserSearch] = useState('')
  const [reportSearch, setReportSearch] = useState('')
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [passwordUser, setPasswordUser] = useState<number | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [isSavingPassword, setIsSavingPassword] = useState(false)

  const [form, setForm] = useState({
    name: '',
    username: '',
    email: '',
    password: '',
    is_admin: false,
  })
  const [isCreating, setIsCreating] = useState(false)

  const { data: users = [], refetch: refetchUsers } = useQuery({
    queryKey: ['users'],
    queryFn: getUsers,
  })

  const { data: myReports = [] } = useQuery({
    queryKey: ['reports'],
    queryFn: getReports,
    enabled: tab === 'my-reports',
  })

  const { data: userReports = [] } = useQuery({
    queryKey: ['user-reports', selectedUser?.id],
    queryFn: () => getUserReports(selectedUser!.id),
    enabled: !!selectedUser,
  })

  const filteredUsers = useMemo(() => {
    const term = userSearch.toLowerCase()
    return users.filter(
      (u) =>
        !term ||
        u.name.toLowerCase().includes(term) ||
        u.username.toLowerCase().includes(term),
    )
  }, [users, userSearch])

  const filteredReports = useMemo(() => {
    const reports = selectedUser ? userReports : myReports
    const term = reportSearch.toLowerCase()
    return reports.filter(
      (r) => !term || r.patient_id.toLowerCase().includes(term) || r.patient_name.toLowerCase().includes(term),
    )
  }, [selectedUser, userReports, myReports, reportSearch])

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsCreating(true)
    try {
      await createUser(form)
      toast.success('User created successfully')
      setForm({ name: '', username: '', email: '', password: '', is_admin: false })
      await refetchUsers()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to create user')
    } finally {
      setIsCreating(false)
    }
  }

  const handlePasswordChange = async (e: React.FormEvent, user: AdminUser) => {
    e.preventDefault()
    setIsSavingPassword(true)
    try {
      await updateUserPassword(user.id, newPassword)
      toast.success(`Password updated for ${user.name}`)
      setPasswordUser(null)
      setNewPassword('')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to update password')
    } finally {
      setIsSavingPassword(false)
    }
  }

  const handleDeleteDoctor = async (user: AdminUser) => {
    if (!window.confirm(`Delete Dr. ${user.name} and all of their reports? This cannot be undone.`)) return
    try {
      await deleteDoctor(user.id)
      toast.success('Doctor and their reports deleted')
      if (selectedUser?.id === user.id) setSelectedUser(null)
      await refetchUsers()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to delete doctor')
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        <h1 className="text-3xl font-bold text-primary-dark mb-1">
          Admin Dashboard
          <span className="ml-2 text-xs text-red-500 border border-red-500 px-2 py-0.5 rounded align-middle">ADMIN</span>
        </h1>
        <p className="text-primary font-medium mb-6">Logged in as {name}</p>

        <div className="flex gap-4 border-b border-slate-200 mb-8">
          {(['users', 'my-reports'] as const).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setSelectedUser(null) }}
              className={`pb-2 px-4 font-semibold cursor-pointer bg-transparent border-none border-b-2 transition-colors ${
                tab === t
                  ? 'text-primary border-primary'
                  : 'text-slate-400 border-transparent hover:text-slate-600'
              }`}
            >
              {t === 'users' ? 'Manage Users' : 'My Reports'}
            </button>
          ))}
        </div>

        {tab === 'users' && !selectedUser && (
          <div className="grid lg:grid-cols-[1fr_2fr] gap-8">
            <div className="glass-panel p-6">
              <h2 className="text-xl font-bold text-primary-dark mb-4">Add New Doctor</h2>
              <form onSubmit={handleCreateUser} className="space-y-4">
                <div>
                  <label className="form-label">Full Name</label>
                  <input className="form-control" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Dr. John Doe" />
                </div>
                <div>
                  <label className="form-label">Username</label>
                  <input className="form-control" required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
                </div>
                <div>
                  <label className="form-label">Email</label>
                  <input type="email" className="form-control" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <div>
                  <label className="form-label">Password</label>
                  <input type="password" className="form-control" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                </div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={form.is_admin} onChange={(e) => setForm({ ...form, is_admin: e.target.checked })} />
                  <span className="font-medium text-sm">Grant Admin Privileges</span>
                </label>
                <button type="submit" disabled={isCreating} className="btn btn-primary w-full">
                  {isCreating ? 'Creating...' : 'Create Account'}
                </button>
              </form>
            </div>

            <div className="glass-panel p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-bold text-primary-dark m-0">Registered Users</h2>
                <button onClick={() => refetchUsers()} className="btn btn-secondary text-sm py-2 px-4">Refresh</button>
              </div>
              <input
                className="form-control mb-4"
                placeholder="Search users..."
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
              />
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-primary/5">
                      <th className="p-3 font-semibold text-primary-dark">Name</th>
                      <th className="p-3 font-semibold text-primary-dark">Username</th>
                      <th className="p-3 font-semibold text-primary-dark">Email</th>
                      <th className="p-3 font-semibold text-primary-dark">Role</th>
                      <th className="p-3 font-semibold text-primary-dark">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((u) => (
                      <tr
                        key={u.id}
                        className="border-b border-slate-200 cursor-pointer hover:bg-primary/5 transition-colors"
                      >
                        <td className="p-3" onClick={() => setSelectedUser(u)}>{u.name}</td>
                        <td className="p-3" onClick={() => setSelectedUser(u)}>{u.username}</td>
                        <td className="p-3" onClick={() => setSelectedUser(u)}>{u.email}</td>
                        <td className="p-3" onClick={() => setSelectedUser(u)}>{u.is_admin ? 'Admin' : 'Doctor'}</td>
                        <td className="p-3 whitespace-nowrap">
                          <button
                            type="button"
                            className="btn btn-secondary text-sm py-1 px-3"
                            onClick={() => { setPasswordUser(passwordUser === u.id ? null : u.id); setNewPassword('') }}
                          >
                            Change password
                          </button>
                          {!u.is_admin && (
                            <button
                              type="button"
                              className="ml-2 text-sm text-red-600 hover:text-red-800 bg-transparent border-0 cursor-pointer"
                              onClick={() => handleDeleteDoctor(u)}
                            >
                              Delete doctor
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {passwordUser !== null && (() => {
                const user = users.find((u) => u.id === passwordUser)
                if (!user) return null
                return (
                  <form onSubmit={(e) => handlePasswordChange(e, user)} className="mt-5 p-4 rounded-lg bg-primary/5 flex flex-wrap items-end gap-3">
                    <div className="flex-1 min-w-56">
                      <label className="form-label">New password for {user.name}</label>
                      <input
                        type="password"
                        className="form-control"
                        minLength={8}
                        required
                        autoComplete="new-password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                      />
                    </div>
                    <button type="submit" disabled={isSavingPassword} className="btn btn-primary">
                      {isSavingPassword ? 'Saving...' : 'Save password'}
                    </button>
                    <button type="button" onClick={() => setPasswordUser(null)} className="btn btn-secondary">Cancel</button>
                  </form>
                )
              })()}
            </div>
          </div>
        )}

        {(selectedUser || tab === 'my-reports') && (
          <div>
            <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
              <h2 className="text-xl font-bold text-primary-dark m-0">
                {selectedUser ? `Reports for ${selectedUser.name}` : 'My Reports'}
              </h2>
              {selectedUser && (
                <button onClick={() => setSelectedUser(null)} className="btn btn-secondary text-sm py-2 px-4">
                  Back to Users
                </button>
              )}
            </div>
            <input
              className="form-control max-w-sm mb-6"
              placeholder="Search by Patient ID or name..."
              value={reportSearch}
              onChange={(e) => setReportSearch(e.target.value)}
            />
            {filteredReports.length === 0 ? (
              <p className="text-slate-500">No reports found.</p>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredReports.map((r) => (
                  <div key={r.id} onClick={() => navigate(`/reports/${r.id}`)}>
                    <ReportCard report={r} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
