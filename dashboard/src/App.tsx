import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMapEvents } from 'react-leaflet'
import { getHealth, getAttendanceZones, createAttendanceZone, patchAttendanceZone, getAccessPoints, createAccessPoint, patchAccessPoint, getAttendanceRegister, getOverview, getAttendanceReport, getAuditLogs, getSchoolSettings, patchSchoolSettings, type AttendanceRegisterRow, type Overview, type AttendanceReport, type AuditLogResponse, type SchoolSettings } from './services/api'
import { AuthProvider, useAuth } from './services/auth'
import { StaffPage } from './pages/StaffPage'
import { DepartmentPage } from './pages/DepartmentPage'
import { DevicePage } from './pages/DevicePage'
import { SchedulePage } from './pages/SchedulePage'
import { LeavePage } from './pages/LeavePage'
import 'leaflet/dist/leaflet.css'
import './App.css'

type AttendanceZone = {
  id: string
  name: string
  latitude: number | string
  longitude: number | string
  radius_meters: number
  is_active: boolean
}

type AccessPoint = {
  id: string
  attendance_zone: string
  bssid: string
  name: string
  location_notes: string
  is_active: boolean
}

function DashboardHome() {
  const [connection, setConnection] = useState<'checking' | 'connected' | 'unavailable'>('checking')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [overviewError, setOverviewError] = useState('')

  useEffect(() => {
    let active = true
    getHealth()
      .then(() => {
        if (active) setConnection('connected')
      })
      .catch(() => {
        if (active) setConnection('unavailable')
      })
    getOverview()
      .then((data) => { if (active) setOverview(data) })
      .catch((caught) => { if (active) setOverviewError(caught instanceof Error ? caught.message : 'Unable to load overview.') })
    return () => {
      active = false
    }
  }, [])

  return (
    <main className="dashboard-card">
      <p className="eyebrow">School Attendance</p>
      <h1>Administration</h1>
      <p className="intro">
        Operational summary for {overview?.school.name ?? 'your school'}.
      </p>
      <section className="connection" aria-live="polite">
        <span className={`connection-indicator connection-indicator--${connection}`} />
        <div>
          <strong>API connection</strong>
          <p>
            {connection === 'checking' && 'Checking the backend...'}
            {connection === 'connected' && 'Backend is reachable.'}
            {connection === 'unavailable' &&
              'Backend is unavailable. Start the Django API to connect this workspace.'}
          </p>
        </div>
      </section>
      {overviewError && <p role="alert" className="error-message">{overviewError}</p>}
      {overview && (
        <section className="stat-grid" aria-label="School overview">
          <article><strong>{overview.staff.total}</strong><span>Active staff</span></article>
          <article><strong>{overview.attendance.present ?? 0}</strong><span>Present today</span></article>
          <article><strong>{overview.attendance.late ?? 0}</strong><span>Late today</span></article>
          <article><strong>{overview.attendance.absent ?? 0}</strong><span>Absent today</span></article>
          <article><strong>{overview.attendance.on_leave ?? 0}</strong><span>On leave today</span></article>
          <article><strong>{overview.devices.pending}</strong><span>Pending devices</span></article>
          <article><strong>{overview.devices.active}</strong><span>Active devices</span></article>
          <article><strong>{overview.leave.pending}</strong><span>Pending leave requests</span></article>
        </section>
      )}
      <nav className="quick-links" aria-label="Quick navigation">
        <Link to="/network-settings">Network &amp; Location Settings</Link>
      </nav>
    </main>
  )
}

function ZoneMap({
  zones,
  selectedZoneId,
  onZoneSelect,
  selectedCoordinates,
  onMapClick,
}: {
  zones: AttendanceZone[]
  selectedZoneId: string | null
  onZoneSelect: (id: string) => void
  selectedCoordinates: { latitude: number; longitude: number } | null
  onMapClick: (latitude: number, longitude: number) => void
}) {
  const focus = useMemo(() => {
    if (selectedZoneId) {
      const zone = zones.find((item) => item.id === selectedZoneId)
      if (zone) {
        return {
          latitude: Number(zone.latitude),
          longitude: Number(zone.longitude),
        }
      }
    }

    if (zones.length > 0) {
      const zone = zones[0]
      return {
        latitude: Number(zone.latitude),
        longitude: Number(zone.longitude),
      }
    }

    return { latitude: -1.292066, longitude: 36.821946 }
  }, [zones, selectedZoneId])

  function MapClickHandler() {
    useMapEvents({
      click(event) {
        onMapClick(event.latlng.lat, event.latlng.lng)
      },
    })
    return null
  }

  return (
    <div className="map-shell">
      <MapContainer center={[focus.latitude, focus.longitude]} zoom={14} scrollWheelZoom className="map-container">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapClickHandler />
        {zones.map((zone) => (
          <Circle
            key={zone.id}
            center={[Number(zone.latitude), Number(zone.longitude)]}
            radius={zone.radius_meters}
            pathOptions={{
              color: zone.id === selectedZoneId ? '#3156a8' : '#2a6f9c',
              fillColor: zone.id === selectedZoneId ? '#3156a8' : '#2a6f9c',
              fillOpacity: 0.16,
              weight: zone.id === selectedZoneId ? 2.5 : 1.6,
            }}
          />
        ))}
        {zones.map((zone) => (
          <CircleMarker
            key={zone.id}
            center={[Number(zone.latitude), Number(zone.longitude)]}
            radius={8}
            pathOptions={{
              color: zone.id === selectedZoneId ? '#3156a8' : '#0f766e',
              fillColor: zone.id === selectedZoneId ? '#3156a8' : '#0f766e',
              fillOpacity: 1,
            }}
            eventHandlers={{
              click: () => onZoneSelect(zone.id),
            }}
          >
            <Popup>{zone.name}</Popup>
          </CircleMarker>
        ))}
        {selectedCoordinates && (
          <Circle
            center={[selectedCoordinates.latitude, selectedCoordinates.longitude]}
            radius={500}
            pathOptions={{ color: '#c7781a', fillColor: '#c7781a', fillOpacity: 0.12, weight: 1.6 }}
          />
        )}
      </MapContainer>
      <div className="map-legend" aria-label="Map legend">
        <span>
          <i className="legend-swatch legend-swatch--zone" /> Active zone
        </span>
        <span>
          <i className="legend-swatch legend-swatch--draft" /> Draft zone
        </span>
      </div>
    </div>
  )
}

function NetworkSettingsPage() {
  const { user } = useAuth()
  const userRole = user?.role ?? 'STAFF'
  const [zones, setZones] = useState<AttendanceZone[]>([])
  const [zonesLoading, setZonesLoading] = useState(true)
  const [zonesError, setZonesError] = useState('')
  const [zoneError, setZoneError] = useState('')
  const [zoneSuccess, setZoneSuccess] = useState('')
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null)
  const [selectedCoordinates, setSelectedCoordinates] = useState<{ latitude: number; longitude: number } | null>(null)
  const [draftZone, setDraftZone] = useState({
    name: '',
    latitude: '',
    longitude: '',
    radius_meters: '150',
    is_active: true,
  })
  const [savingZone, setSavingZone] = useState(false)
  const [accessPoints, setAccessPoints] = useState<AccessPoint[]>([])
  const [accessPointsLoading, setAccessPointsLoading] = useState(true)
  const [apError, setApError] = useState('')
  const [apSuccess, setApSuccess] = useState('')
  const [selectedAccessPointId, setSelectedAccessPointId] = useState<string | null>(null)
  const [draftAccessPoint, setDraftAccessPoint] = useState({
    name: '',
    bssid: '',
    attendance_zone: '',
    location_notes: '',
  })
  const [savingAccessPoint, setSavingAccessPoint] = useState(false)
  const [apZoneFilter, setApZoneFilter] = useState('all')
  const [apStatusFilter, setApStatusFilter] = useState('all')
  const canManage = userRole === 'SCHOOL_ADMIN'
  const canView = userRole === 'SCHOOL_ADMIN' || userRole === 'ATTENDANCE_MANAGER'

  const loadZones = async () => {
    setZonesLoading(true)
    setZonesError('')
    try {
      const data = await getAttendanceZones()
      setZones(data)
      if (data.length > 0 && !selectedZoneId && selectedCoordinates === null) {
        const first = data[0]
        setSelectedCoordinates({ latitude: Number(first.latitude), longitude: Number(first.longitude) })
      }
    } catch (error) {
      setZonesError(error instanceof Error ? error.message : 'Unable to load attendance zones.')
    } finally {
      setZonesLoading(false)
    }
  }

  const loadAccessPoints = async () => {
    setAccessPointsLoading(true)
    try {
      const data = await getAccessPoints()
      setAccessPoints(data)
      if (data.length > 0 && !selectedAccessPointId) {
        setSelectedAccessPointId(data[0].id)
      }
    } catch (error) {
      setApError(error instanceof Error ? error.message : 'Unable to load access points.')
    } finally {
      setAccessPointsLoading(false)
    }
  }

  useEffect(() => {
    void loadZones()
    void loadAccessPoints()
  }, [])

  useEffect(() => {
    if (!canView) {
      return
    }
    if (zones.length === 0) {
      setSelectedCoordinates(null)
      return
    }
    if (selectedZoneId) {
      const selected = zones.find((zone) => zone.id === selectedZoneId)
      if (selected) {
        setSelectedCoordinates({ latitude: Number(selected.latitude), longitude: Number(selected.longitude) })
      }
      return
    }
    if (selectedCoordinates === null) {
      const first = zones[0]
      setSelectedCoordinates({ latitude: Number(first.latitude), longitude: Number(first.longitude) })
    }
  }, [canView, selectedCoordinates, selectedZoneId, zones])

  const selectedZone = zones.find((zone) => zone.id === selectedZoneId) ?? null

  const fillZoneDraft = (zone: AttendanceZone | null) => {
    if (!zone) {
      setSelectedZoneId(null)
      setSelectedCoordinates(null)
      setDraftZone({ name: '', latitude: '', longitude: '', radius_meters: '150', is_active: true })
      return
    }

    setSelectedZoneId(zone.id)
    setSelectedCoordinates({ latitude: Number(zone.latitude), longitude: Number(zone.longitude) })
    setDraftZone({
      name: zone.name,
      latitude: String(zone.latitude),
      longitude: String(zone.longitude),
      radius_meters: String(zone.radius_meters),
      is_active: zone.is_active,
    })
  }

  const handleZoneSelect = (zoneId: string) => {
    const zone = zones.find((item) => item.id === zoneId)
    if (!zone) return
    fillZoneDraft(zone)
  }

  const handleMapClick = (latitude: number, longitude: number) => {
    setSelectedCoordinates({ latitude, longitude })
    setDraftZone((previous) => ({
      ...previous,
      latitude: String(latitude),
      longitude: String(longitude),
    }))
    if (selectedZoneId) {
      setSelectedZoneId(null)
    }
  }

  const handleSaveZone = async (event: React.FormEvent) => {
    event.preventDefault()
    setZoneError('')
    setZoneSuccess('')
    const name = draftZone.name.trim()
    const latitude = Number(draftZone.latitude)
    const longitude = Number(draftZone.longitude)
    const radius_meters = Number(draftZone.radius_meters)

    if (!name || Number.isNaN(latitude) || Number.isNaN(longitude) || Number.isNaN(radius_meters)) {
      setZoneError('Enter a valid zone name, latitude, longitude and radius before saving.')
      return
    }

    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180 || radius_meters <= 0) {
      setZoneError('Latitude and longitude must be within valid world coordinates and the radius must be greater than zero.')
      return
    }

    setSavingZone(true)

    try {
      if (selectedZoneId) {
        const payload = {
          name,
          latitude: String(latitude),
          longitude: String(longitude),
          radius_meters,
          is_active: draftZone.is_active,
        }
        await patchAttendanceZone(selectedZoneId, payload)
        setZoneSuccess('Zone updated successfully.')
      } else {
        const payload = {
          name,
          latitude: String(latitude),
          longitude: String(longitude),
          radius_meters,
          is_active: draftZone.is_active,
        }
        const created = await createAttendanceZone(payload)
        setSelectedZoneId(created.id)
        setZoneSuccess('Zone created successfully.')
      }
      await loadZones()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Zone update failed.'
      setZoneError(message)
    } finally {
      setSavingZone(false)
    }
  }

  const handleToggleZone = async (zoneId: string) => {
    const zone = zones.find((item) => item.id === zoneId)
    if (!zone) return
    try {
      await patchAttendanceZone(zoneId, { is_active: !zone.is_active })
      await loadZones()
      setZoneSuccess(`Zone ${zone.name} was ${zone.is_active ? 'deactivated' : 'activated'}.`)
    } catch (error) {
      setZoneError(error instanceof Error ? error.message : 'Unable to update zone status.')
    }
  }

  const handleAccessPointSelect = (id: string) => {
    const selection = accessPoints.find((point) => point.id === id)
    if (!selection) return
    setSelectedAccessPointId(id)
    setDraftAccessPoint({
      name: selection.name,
      bssid: selection.bssid,
      attendance_zone: selection.attendance_zone,
      location_notes: selection.location_notes,
    })
  }

  const handleSaveAccessPoint = async (event: React.FormEvent) => {
    event.preventDefault()
    setApError('')
    setApSuccess('')
    const name = draftAccessPoint.name.trim()
    const bssid = draftAccessPoint.bssid.trim()
    const attendance_zone = draftAccessPoint.attendance_zone
    const location_notes = draftAccessPoint.location_notes.trim()

    if (!(name && bssid && attendance_zone)) {
      setApError('Name, BSSID and attendance zone are required.')
      return
    }

    setSavingAccessPoint(true)

    try {
      if (selectedAccessPointId) {
        await patchAccessPoint(selectedAccessPointId, {
          name,
          location_notes,
          is_active: true,
        })
        setApSuccess('Access point updated successfully.')
      } else {
        await createAccessPoint({
          name,
          bssid,
          attendance_zone,
          location_notes,
        })
        setApSuccess('Access point registered successfully.')
      }
      setDraftAccessPoint({ name: '', bssid: '', attendance_zone: '', location_notes: '' })
      setSelectedAccessPointId(null)
      await loadAccessPoints()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to save access point.'
      setApError(message)
    } finally {
      setSavingAccessPoint(false)
    }
  }

  const handleToggleAccessPoint = async (pointId: string) => {
    const point = accessPoints.find((item) => item.id === pointId)
    if (!point) return

    try {
      await patchAccessPoint(pointId, { is_active: !point.is_active })
      await loadAccessPoints()
      setApSuccess(`Access point ${point.name} was ${point.is_active ? 'deactivated' : 'activated'}.`)
    } catch (error) {
      setApError(error instanceof Error ? error.message : 'Unable to update access point status.')
    }
  }

  const filteredAccessPoints = accessPoints.filter((point) => {
    const matchesZone = apZoneFilter === 'all' || point.attendance_zone === apZoneFilter
    const matchesStatus =
      apStatusFilter === 'all' ||
      (apStatusFilter === 'active' && point.is_active) ||
      (apStatusFilter === 'inactive' && !point.is_active)
    return matchesZone && matchesStatus
  })

  if (!canView) {
    return (
      <main className="dashboard-card">
        <p className="eyebrow">Network &amp; Location Settings</p>
        <h1>Access denied</h1>
        <p className="intro">Staff members cannot access this dashboard module.</p>
        <Link to="/">Return to administration</Link>
      </main>
    )
  }

  return (
    <main className="network-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Location settings</p>
          <h1>Network &amp; Location Settings</h1>
        </div>
      </header>

      <section className="panel-grid">
        <div className="panel panel--wide">
          <div className="panel-heading">
            <h2>Attendance Zones</h2>
            {!canManage && <span className="read-only-badge">Read only</span>}
          </div>

          {zonesLoading ? (
            <div className="state-card">Loading zones…</div>
          ) : zonesError ? (
            <div className="state-card state-card--error">{zonesError}</div>
          ) : (
            <>
              <ZoneMap
                zones={zones}
                selectedZoneId={selectedZoneId}
                onZoneSelect={handleZoneSelect}
                selectedCoordinates={selectedCoordinates}
                onMapClick={handleMapClick}
              />

              <div className="zone-list">
                {zones.length === 0 ? (
                  <div className="state-card">No attendance zones have been configured yet.</div>
                ) : (
                  zones.map((zone) => (
                    <div
                      key={zone.id}
                      className={`zone-item ${selectedZone?.id === zone.id ? 'zone-item--selected' : ''}`}
                    >
                      <button type="button" className="zone-select" onClick={() => handleZoneSelect(zone.id)}>
                        <span className="zone-name">{zone.name}</span>
                        <span className="zone-meta">
                          {Number(zone.latitude).toFixed(5)}, {Number(zone.longitude).toFixed(5)} • {zone.radius_meters}m
                        </span>
                        <span className={`status-pill ${zone.is_active ? 'status-pill--active' : 'status-pill--inactive'}`}>
                          {zone.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </button>
                      {canManage && (
                        <button
                          type="button"
                          className="secondary-button zone-action"
                          onClick={() => void handleToggleZone(zone.id)}
                        >
                          {zone.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          <form className="config-form" onSubmit={handleSaveZone}>
            <div className="field-row">
              <label>
                Zone name
                <input
                  type="text"
                  value={draftZone.name}
                  onChange={(event) => setDraftZone((previous) => ({ ...previous, name: event.target.value }))}
                  disabled={!canManage}
                  aria-label="Zone name"
                />
              </label>
            </div>
            <div className="field-row field-row--split">
              <label>
                Latitude
                <input
                  type="number"
                  step="0.000001"
                  value={draftZone.latitude}
                  onChange={(event) => setDraftZone((previous) => ({ ...previous, latitude: event.target.value }))}
                  disabled={!canManage}
                  aria-label="Latitude"
                />
              </label>
              <label>
                Longitude
                <input
                  type="number"
                  step="0.000001"
                  value={draftZone.longitude}
                  onChange={(event) => setDraftZone((previous) => ({ ...previous, longitude: event.target.value }))}
                  disabled={!canManage}
                  aria-label="Longitude"
                />
              </label>
            </div>
            <div className="field-row field-row--split">
              <label>
                Radius (metres)
                <input
                  type="number"
                  min="1"
                  value={draftZone.radius_meters}
                  onChange={(event) => setDraftZone((previous) => ({ ...previous, radius_meters: event.target.value }))}
                  disabled={!canManage}
                  aria-label="Radius in metres"
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={draftZone.is_active}
                  onChange={(event) => setDraftZone((previous) => ({ ...previous, is_active: event.target.checked }))}
                  disabled={!canManage}
                />
                Active zone
              </label>
            </div>

            {zoneError && <div className="feedback feedback--error">{zoneError}</div>}
            {zoneSuccess && <div className="feedback feedback--success">{zoneSuccess}</div>}

            {canManage && (
              <div className="button-row">
                <button type="submit" className="primary-button" disabled={savingZone}>
                  {savingZone ? 'Saving…' : selectedZoneId ? 'Save zone' : 'Create zone'}
                </button>
                <button type="button" className="secondary-button" onClick={() => fillZoneDraft(null)}>
                  Clear
                </button>
              </div>
            )}
          </form>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <h2>Wi‑Fi Access Points</h2>
            {!canManage && <span className="read-only-badge">Read only</span>}
          </div>

          {accessPointsLoading ? (
            <div className="state-card">Loading access points…</div>
          ) : accessPoints.length === 0 ? (
            <div className="state-card">No access points are registered for this school.</div>
          ) : (
            <div className="filters">
              <label>
                Zone
                <select value={apZoneFilter} onChange={(event) => setApZoneFilter(event.target.value)}>
                  <option value="all">All zones</option>
                  {zones.map((zone) => (
                    <option key={zone.id} value={zone.id}>
                      {zone.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select value={apStatusFilter} onChange={(event) => setApStatusFilter(event.target.value)}>
                  <option value="all">All states</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </label>
            </div>
          )}

          <div className="ap-list">
            {filteredAccessPoints.map((point) => {
              const zoneName = zones.find((zone) => zone.id === point.attendance_zone)?.name ?? 'Unknown zone'
              return (
                <div key={point.id} className={`ap-item ${selectedAccessPointId === point.id ? 'ap-item--selected' : ''}`}>
                  <div className="ap-item__head">
                    <strong>{point.name}</strong>
                    <span className={`status-pill ${point.is_active ? 'status-pill--active' : 'status-pill--inactive'}`}>
                      {point.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <div className="ap-item__meta">BSSID: {point.bssid}</div>
                  <div className="ap-item__meta">Zone: {zoneName}</div>
                  {point.location_notes && <div className="ap-item__meta">Notes: {point.location_notes}</div>}
                  <div className="ap-item__actions">
                    <button type="button" className="secondary-button" onClick={() => handleAccessPointSelect(point.id)}>
                      Edit
                    </button>
                    {canManage && (
                      <button type="button" className="secondary-button" onClick={() => void handleToggleAccessPoint(point.id)}>
                        {point.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          <form className="config-form" onSubmit={handleSaveAccessPoint}>
            <div className="field-row">
              <label>
                Access point name
                <input
                  type="text"
                  value={draftAccessPoint.name}
                  onChange={(event) => setDraftAccessPoint((previous) => ({ ...previous, name: event.target.value }))}
                  disabled={!canManage}
                  aria-label="Access point name"
                />
              </label>
            </div>
            <div className="field-row">
              <label>
                BSSID
                <input
                  type="text"
                  value={draftAccessPoint.bssid}
                  onChange={(event) => setDraftAccessPoint((previous) => ({ ...previous, bssid: event.target.value }))}
                  disabled={!canManage}
                  aria-label="Access point BSSID"
                />
              </label>
            </div>
            <div className="field-row">
              <label>
                Attendance zone
                <select
                  value={draftAccessPoint.attendance_zone}
                  onChange={(event) => setDraftAccessPoint((previous) => ({ ...previous, attendance_zone: event.target.value }))}
                  disabled={!canManage || zones.length === 0}
                  aria-label="Attendance zone"
                >
                  <option value="">Select a zone</option>
                  {zones.map((zone) => (
                    <option key={zone.id} value={zone.id}>
                      {zone.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="field-row">
              <label>
                Location notes
                <textarea
                  rows={3}
                  value={draftAccessPoint.location_notes}
                  onChange={(event) => setDraftAccessPoint((previous) => ({ ...previous, location_notes: event.target.value }))}
                  disabled={!canManage}
                  aria-label="Location notes"
                />
              </label>
            </div>

            {apError && <div className="feedback feedback--error">{apError}</div>}
            {apSuccess && <div className="feedback feedback--success">{apSuccess}</div>}

            {canManage && (
              <div className="button-row">
                <button type="submit" className="primary-button" disabled={savingAccessPoint}>
                  {savingAccessPoint ? 'Saving…' : selectedAccessPointId ? 'Update access point' : 'Register access point'}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setSelectedAccessPointId(null)
                    setDraftAccessPoint({ name: '', bssid: '', attendance_zone: '', location_notes: '' })
                  }}
                >
                  Clear
                </button>
              </div>
            )}
          </form>
        </div>
      </section>
    </main>
  )
}

function NotFound() {
  return (
    <main className="dashboard-card">
      <h1>Page not found</h1>
      <Link to="/">Return to administration</Link>
    </main>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

function LoginPage() {
  const { login, staffRejected, clearStaffRejected } = useAuth()
  const [schoolCode, setSchoolCode] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const location = useLocation()

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    clearStaffRejected()
    if (!schoolCode.trim() || !username.trim() || !password) {
      setError('School code, username and password are required.')
      return
    }
    setLoading(true)
    try {
      await login(schoolCode, username, password)
    } catch (loginError) {
      if (loginError instanceof Error && loginError.message === 'STAFF_ONLY') {
        return
      }
      setError(loginError instanceof Error ? loginError.message : 'Unable to sign in.')
    } finally {
      setLoading(false)
    }
  }

  const destination = (location.state as { from?: string } | null)?.from ?? '/'

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-heading">
        <div className="login-brand"><span className="brand-mark" aria-hidden="true">SA</span><span>School Attendance</span></div>
        <p className="eyebrow">Administration portal</p>
        <h1 id="login-heading">Sign in</h1>
        <p className="intro">Enter your school credentials to continue.</p>
        {staffRejected && (
          <div className="feedback feedback--error" role="alert">
            Staff attendance is handled through the mobile application. This web portal is for school administrators and attendance managers.
          </div>
        )}
        <form className="login-form" onSubmit={submit} noValidate>
          <label htmlFor="school-code">School code
            <input id="school-code" value={schoolCode} onChange={(event) => setSchoolCode(event.target.value)} autoComplete="organization" />
          </label>
          <label htmlFor="username">Username
            <input id="username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label htmlFor="password">Password
            <span className="password-field">
              <input id="password" type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
              <button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword((shown) => !shown)}>
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </span>
          </label>
          {error && <div className="feedback feedback--error" role="alert">{error}</div>}
          <button type="submit" className="primary-button login-submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <span className="login-destination" hidden>{destination}</span>
      </section>
    </main>
  )
}

function ProtectedRoute({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) {
  const { user, restoring } = useAuth()
  const location = useLocation()
  if (restoring) return <main className="dashboard-card"><div className="state-card">Restoring your session…</div></main>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (adminOnly && user.role !== 'SCHOOL_ADMIN') return <Navigate to="/" replace />
  return <>{children}</>
}

function AttendanceRegisterPage() {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [rows, setRows] = useState<AttendanceRegisterRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    getAttendanceRegister(date)
      .then((next) => { if (active) setRows(next) })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Unable to load attendance.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [date])

  return (
    <main className="dashboard-card">
      <p className="eyebrow">Read-only attendance</p>
      <h1>Attendance Register</h1>
      <label>Date <input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label>
      {loading && <p role="status">Loading attendance...</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
      {!loading && !error && (
        rows.length === 0 ? <p>No staff or attendance records for this date.</p> : (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Staff</th><th>Department</th><th>Status</th><th>Check-in</th><th>Check-out</th></tr></thead>
              <tbody>{rows.map((row) => (
                <tr key={row.staff_id}>
                  <td>{row.staff_name} ({row.employee_number})</td>
                  <td>{row.department ?? 'Unassigned'}</td>
                  <td>{row.status}</td>
                  <td>{row.check_in ? new Date(row.check_in).toLocaleTimeString() : '-'}</td>
                  <td>{row.check_out ? new Date(row.check_out).toLocaleTimeString() : '-'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )
      )}
    </main>
  )
}

function ReportsPage() {
  const [dateFrom, setDateFrom] = useState(() => new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10))
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10))
  const [report, setReport] = useState<AttendanceReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    getAttendanceReport(dateFrom, dateTo)
      .then((next) => { if (active) setReport(next); setError('') })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Unable to load report.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [dateFrom, dateTo])

  function exportCsv() {
    if (!report) return
    const headers = ['Employee number', 'First name', 'Last name', 'Department', 'Records', 'Present', 'Late', 'Absent', 'On leave', 'Incomplete']
    const rows = report.by_staff.map((row) => [
      row.staff_profile__employee_number,
      row.staff_profile__first_name,
      row.staff_profile__last_name,
      row.staff_profile__department__name ?? '',
      row.records,
      row.present,
      row.late,
      row.absent,
      row.on_leave,
      row.incomplete,
    ])
    const csv = [headers, ...rows].map((row) => row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `attendance-${dateFrom}-to-${dateTo}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <main className="dashboard-card">
      <p className="eyebrow">Stored attendance data</p>
      <h1>Reports</h1>
      <div className="filter-row">
        <label>From <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
        <label>To <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
        <button type="button" disabled={!report} onClick={exportCsv}>Export CSV</button>
      </div>
      {loading && <p role="status">Loading report...</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
      {report && !loading && (
        <>
          <div className="stat-grid">
            {report.summary.map((item) => <article key={item.status}><strong>{item.count}</strong><span>{item.status}</span></article>)}
          </div>
          {report.by_staff.length === 0 ? <p>No attendance records in this date range.</p> : (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Staff</th><th>Department</th><th>Records</th><th>Present</th><th>Late</th><th>Absent</th><th>Leave</th><th>Incomplete</th></tr></thead>
                <tbody>{report.by_staff.map((row) => (
                  <tr key={row.staff_profile__employee_number}>
                    <td>{row.staff_profile__first_name} {row.staff_profile__last_name} ({row.staff_profile__employee_number})</td>
                    <td>{row.staff_profile__department__name ?? 'Unassigned'}</td>
                    <td>{row.records}</td><td>{row.present}</td><td>{row.late}</td><td>{row.absent}</td><td>{row.on_leave}</td><td>{row.incomplete}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  )
}

function AuditLogsPage() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [action, setAction] = useState('')
  const [logs, setLogs] = useState<AuditLogResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    getAuditLogs({ page, pageSize: 25, search, action })
      .then((next) => { if (active) { setLogs(next); setError('') } })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Unable to load audit logs.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [page, search, action])

  return (
    <main className="dashboard-card">
      <p className="eyebrow">Append-only history</p>
      <h1>Audit Logs</h1>
      <div className="filter-row">
        <label>Search <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} /></label>
        <label>Action <input value={action} onChange={(event) => { setAction(event.target.value); setPage(1) }} /></label>
      </div>
      {loading && <p role="status">Loading audit history...</p>}
      {error && <p role="alert" className="error-message">{error}</p>}
      {logs && !loading && (
        <>
          {logs.results.length === 0 ? <p>No audit entries match the filters.</p> : (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Time</th><th>Action</th><th>Entity</th><th>Actor</th><th>Reason</th></tr></thead>
                <tbody>{logs.results.map((log) => (
                  <tr key={log.id}>
                    <td>{new Date(log.created_at).toLocaleString()}</td>
                    <td>{log.action}</td>
                    <td>{log.entity_type} ({log.entity_id})</td>
                    <td>{log.actor_user_id ?? 'Operator / system'}</td>
                    <td>{log.reason || '-'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <div className="pagination">
            <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <span>Page {logs.page} of {Math.max(logs.total_pages, 1)}</span>
            <button type="button" disabled={page >= logs.total_pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </>
      )}
    </main>
  )
}

function SchoolSettingsPage() {
  const [settings, setSettings] = useState<SchoolSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    let active = true
    getSchoolSettings()
      .then((next) => { if (active) setSettings(next) })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Unable to load school settings.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!settings) return
    setSaving(true); setError(''); setSuccess('')
    try {
      const next = await patchSchoolSettings({
        name: settings.name,
        email: settings.email,
        phone: settings.phone,
        address: settings.address,
        timezone: settings.timezone,
      })
      setSettings(next)
      setSuccess('School settings saved.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save school settings.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <main className="dashboard-card"><p role="status">Loading school settings...</p></main>
  if (!settings) return <main className="dashboard-card"><p role="alert" className="error-message">{error || 'Settings unavailable.'}</p></main>
  return (
    <main className="dashboard-card">
      <p className="eyebrow">School configuration</p>
      <h1>School Settings</h1>
      <p>School code: <strong>{settings.school_code}</strong></p>
      <p>Status: <strong>{settings.status}</strong></p>
      <form onSubmit={save}>
        <label>School name <input value={settings.name} onChange={(event) => setSettings({ ...settings, name: event.target.value })} required /></label>
        <label>Email <input type="email" value={settings.email} onChange={(event) => setSettings({ ...settings, email: event.target.value })} /></label>
        <label>Phone <input value={settings.phone} onChange={(event) => setSettings({ ...settings, phone: event.target.value })} /></label>
        <label>Address <textarea value={settings.address} onChange={(event) => setSettings({ ...settings, address: event.target.value })} /></label>
        <label>Timezone <input value={settings.timezone} onChange={(event) => setSettings({ ...settings, timezone: event.target.value })} required /></label>
        {error && <p role="alert" className="error-message">{error}</p>}
        {success && <p aria-live="polite">{success}</p>}
        <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save settings'}</button>
      </form>
    </main>
  )
}

function AdministrationShell() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />

  const navItems = [
    { path: '/', label: 'Overview', show: true },
    { path: '/attendance', label: 'Attendance Register', show: true },
    { path: '/staff', label: 'Staff Management', show: user.role === 'SCHOOL_ADMIN' },
    { path: '/departments', label: 'Departments', show: true },
    { path: '/devices', label: 'Device Management', show: user.role === 'SCHOOL_ADMIN' },
    { path: '/network-settings', label: 'Network & Location Settings', show: true },
    { path: '/schedules', label: 'Schedules', show: true },
    { path: '/leave', label: 'Leave Management', show: true },
    { path: '/reports', label: 'Reports', show: user.role === 'SCHOOL_ADMIN' },
    { path: '/audit', label: 'Audit Logs', show: user.role === 'SCHOOL_ADMIN' },
    { path: '/school-settings', label: 'School Settings', show: user.role === 'SCHOOL_ADMIN' },
  ]

  return (
    <div className="app-shell app-shell--authenticated">
      <aside className={`sidebar ${menuOpen ? 'sidebar--open' : ''}`}>
        <Link className="brand sidebar-brand" to="/" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark" aria-hidden="true">SA</span>
          <span>School Attendance</span>
        </Link>
        <nav className="side-nav" aria-label="Dashboard navigation">
          {navItems.filter((item) => item.show).map((item) => (
            <Link key={item.path} to={item.path} className={location.pathname === item.path ? 'active' : ''} onClick={() => setMenuOpen(false)}>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-user">
          <strong>{user.username}</strong>
          <span>{user.role}</span>
          <span>{user.school_code}</span>
          <button type="button" className="secondary-button" onClick={() => void logout()}>Log out</button>
        </div>
      </aside>
      <button type="button" className="mobile-menu-button" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
        {menuOpen ? 'Close menu' : 'Menu'}
      </button>
      <div className="main-column">
        <Routes>
          <Route path="/" element={<ProtectedRoute><DashboardHome /></ProtectedRoute>} />
          <Route path="/staff" element={<ProtectedRoute adminOnly><StaffPage /></ProtectedRoute>} />
          <Route path="/departments" element={<ProtectedRoute><DepartmentPage /></ProtectedRoute>} />
          <Route path="/network-settings" element={<ProtectedRoute><NetworkSettingsPage /></ProtectedRoute>} />
          <Route path="/attendance" element={<ProtectedRoute><AttendanceRegisterPage /></ProtectedRoute>} />
          <Route path="/devices" element={<ProtectedRoute adminOnly><DevicePage /></ProtectedRoute>} />
          <Route path="/schedules" element={<ProtectedRoute><SchedulePage /></ProtectedRoute>} />
          <Route path="/leave" element={<ProtectedRoute><LeavePage /></ProtectedRoute>} />
          <Route path="/reports" element={<ProtectedRoute adminOnly><ReportsPage /></ProtectedRoute>} />
          <Route path="/audit" element={<ProtectedRoute adminOnly><AuditLogsPage /></ProtectedRoute>} />
          <Route path="/school-settings" element={<ProtectedRoute adminOnly><SchoolSettingsPage /></ProtectedRoute>} />
          <Route path="*" element={<ProtectedRoute><NotFound /></ProtectedRoute>} />
        </Routes>
      </div>
    </div>
  )
}

function AppRoutes() {
  const { user, restoring } = useAuth()
  if (restoring) return <main className="dashboard-card"><div className="state-card">Restoring your session…</div></main>
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="*" element={<AdministrationShell />} />
    </Routes>
  )
}
