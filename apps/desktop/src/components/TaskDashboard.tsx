import { DashboardTareasMessage, DashboardTask, TaskDashboardStatus } from "@/lib/protocol";

interface TaskDashboardProps {
  dashboard: DashboardTareasMessage;
  onClose: () => void;
}

const DAY_MS = 24 * 60 * 60 * 1000;

const STATUS_LABEL: Record<TaskDashboardStatus, string> = {
  completada: "Completada",
  vencida: "Vencida",
  hoy: "Vence hoy",
  programada: "Programada",
  sin_fecha: "Sin fecha",
};

function parseDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function dayDistance(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / DAY_MS);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("es", { day: "2-digit", month: "short", timeZone: "UTC" }).format(parseDate(value));
}

function taskDates(task: DashboardTask): [Date, Date] | null {
  if (!task.fecha_inicio || !task.fecha_fin) return null;
  return [parseDate(task.fecha_inicio), parseDate(task.fecha_fin)];
}

export function TaskDashboard({ dashboard, onClose }: TaskDashboardProps) {
  const overallProgress = dashboard.resumen.total
    ? Math.round((dashboard.resumen.completadas / dashboard.resumen.total) * 100)
    : 0;
  const scheduledTasks = dashboard.tareas.filter((task) => taskDates(task) !== null);
  const unscheduledTasks = dashboard.tareas.filter((task) => taskDates(task) === null);
  const allDates = scheduledTasks.flatMap((task) => taskDates(task) ?? []);
  const rangeStart = allDates.length ? new Date(Math.min(...allDates.map((date) => date.getTime()))) : null;
  const rangeEnd = allDates.length ? new Date(Math.max(...allDates.map((date) => date.getTime()))) : null;
  const totalDays = rangeStart && rangeEnd ? Math.max(1, dayDistance(rangeStart, rangeEnd) + 1) : 0;
  const today = parseDate(dashboard.fecha_referencia);
  const tickOffsets = totalDays
    ? Array.from(new Set([0, Math.round((totalDays - 1) / 4), Math.round((totalDays - 1) / 2), Math.round((totalDays - 1) * 0.75), totalDays - 1]))
    : [];
  const todayOffset = rangeStart && rangeEnd && today >= rangeStart && today <= rangeEnd ? dayDistance(rangeStart, today) : null;

  return (
    <section className="task-dashboard" aria-labelledby="task-dashboard-title">
      <header className="task-dashboard-header">
        <div>
          <span className="task-dashboard-kicker">PLANIFICACIÓN</span>
          <h2 id="task-dashboard-title">Dashboard de tareas</h2>
          <p>Actualizado al {new Intl.DateTimeFormat("es", { dateStyle: "long", timeZone: "UTC" }).format(today)}.</p>
        </div>
        <button className="dashboard-close" type="button" onClick={onClose} aria-label="Cerrar dashboard de tareas">
          Cerrar
        </button>
      </header>

      <div className="task-dashboard-summary" aria-label="Resumen de tareas">
        <span><strong>{dashboard.resumen.pendientes}</strong> pendientes</span>
        <span><strong>{dashboard.resumen.completadas}</strong> completadas</span>
        <span className={dashboard.resumen.vencidas ? "summary-alert" : ""}><strong>{dashboard.resumen.vencidas}</strong> vencidas</span>
        <span><strong>{dashboard.resumen.sin_fecha}</strong> sin fecha</span>
      </div>
      <div className="dashboard-progress" aria-label={`Progreso total: ${overallProgress}%`}>
        <div className="dashboard-progress-label"><span>Progreso total</span><strong>{overallProgress}%</strong></div>
        <div className="dashboard-progress-track"><span style={{ width: `${overallProgress}%` }} /></div>
      </div>

      {scheduledTasks.length > 0 ? (
        <div className="gantt" role="region" aria-label="Diagrama de Gantt de tareas calendarizadas">
          <div className="gantt-heading">
            <h3>Calendario y progreso</h3>
            <span>{formatDate(rangeStart!.toISOString().slice(0, 10))} — {formatDate(rangeEnd!.toISOString().slice(0, 10))}</span>
          </div>
          <div className="gantt-axis" aria-hidden="true">
            {tickOffsets.map((offset) => {
              const tickDate = new Date(rangeStart!.getTime() + offset * DAY_MS).toISOString().slice(0, 10);
              return <span key={offset} style={{ left: `${(offset / Math.max(1, totalDays - 1)) * 100}%` }}>{formatDate(tickDate)}</span>;
            })}
          </div>
          <div className="gantt-rows">
            {scheduledTasks.map((task) => {
              const [start, end] = taskDates(task)!;
              const left = (dayDistance(rangeStart!, start) / totalDays) * 100;
              const width = Math.max(2.5, ((dayDistance(start, end) + 1) / totalDays) * 100);
              return (
                <div className="gantt-row" key={task.id}>
                  <div className="gantt-task-name">
                    <span>{task.titulo}</span>
                    <small>{task.ruta} · {formatDate(task.fecha_fin!)}{task.alertas.length > 0 ? " · ⚠ revisar fechas" : ""}</small>
                  </div>
                  <div className="gantt-track">
                    {todayOffset !== null && <i className="gantt-today" style={{ left: `${(todayOffset / totalDays) * 100}%` }} />}
                    <div className={`gantt-bar status-${task.estado}`} style={{ left: `${left}%`, width: `${width}%` }} aria-label={`${task.titulo}: ${STATUS_LABEL[task.estado]}, ${task.progreso}%`}>
                      {task.progreso === 100 && <span>✓</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="gantt-legend" aria-label="Leyenda">
            <span><i className="status-programada" /> Programada</span>
            <span><i className="status-hoy" /> Vence hoy</span>
            <span><i className="status-vencida" /> Vencida</span>
            <span><i className="status-completada" /> Completada</span>
          </div>
        </div>
      ) : (
        <p className="dashboard-empty">Todavía no hay tareas calendarizadas. Agregá `🛫 AAAA-MM-DD` y/o `📅 AAAA-MM-DD` a una tarea para verla en el Gantt.</p>
      )}

      {unscheduledTasks.length > 0 && (
        <div className="unscheduled-tasks">
          <h3>Por calendarizar</h3>
          {unscheduledTasks.map((task) => (
            <div className="unscheduled-task" key={task.id}>
              <span>{task.titulo}</span>
              <small>{task.ruta}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
