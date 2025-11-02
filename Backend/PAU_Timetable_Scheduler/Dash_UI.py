import os
import json
import io
import dash
import pandas as pd
import shutil
import traceback
import time
import dash.exceptions
import dash.dependencies
from dash import dcc, html, Input, Output, State, clientside_callback

# Optional: import input_data to support lecturer lookups like the original UI
try:
    from input_data import input_data
except Exception:
    input_data = None


def _load_rooms_data():
    try:
        path = os.path.join(os.path.dirname(__file__), 'data', 'rooms-data.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _load_saved_timetable():
    """Prefer fresh_timetable_data.json, else fallback to backend-saved timetable_data.json."""
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    session_path = os.path.join(data_dir, 'timetable_data.json')
    fresh_path = os.path.join(data_dir, 'fresh_timetable_data.json')

    # Prefer fresh results from the latest optimization
    try:
        if os.path.exists(fresh_path):
            with open(fresh_path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            # fresh is expected to be a list of timetables
            if isinstance(saved, list):
                return saved, []
            # handle legacy dict formats defensively
            if isinstance(saved, dict) and 'timetables' in saved:
                return saved.get('timetables', []), saved.get('manual_cells', []) or []
    except Exception:
        pass

    # Fallback to last session's saved data (includes manual_cells)
    try:
        if os.path.exists(session_path):
            with open(session_path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            if isinstance(saved, dict) and 'timetables' in saved:
                return saved.get('timetables', []), saved.get('manual_cells', [])
            # old format: list
            if isinstance(saved, list):
                return saved, []
    except Exception:
        pass

    return [], []


def _extract_room(cell_content):
    if not cell_content or str(cell_content).strip().upper() in ("FREE", "BREAK"):
        return None
    parts = str(cell_content).split('\n')
    if len(parts) > 1 and parts[1].strip():
        room = parts[1].strip()
        # Normalize like OG (handle optional prefix)
        room = room.replace('Room:', '').strip()
        return room or None
    return None


def _extract_course_and_faculty(cell_content):
    if not cell_content or str(cell_content).strip().upper() in ("FREE", "BREAK"):
        return None, None
    parts = str(cell_content).split('\n')
    course = parts[0].strip() if len(parts) > 0 and parts[0].strip() else None
    faculty = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    # Normalize like OG (strip common prefixes and whitespace)
    if course:
        course = course.replace('Course:', '').strip()
    if faculty:
        faculty = faculty.replace('Lecturer:', '').strip()
    return course, faculty


def _detect_conflicts(all_timetables, current_group_idx):
    conflicts = {}
    if not all_timetables:
        return conflicts

    current_timetable = all_timetables[current_group_idx]['timetable']
    for row_idx in range(len(current_timetable)):
        for col_idx in range(1, len(current_timetable[row_idx])):
            key = f"{row_idx}_{col_idx-1}"
            room_usage = {}
            lecturer_usage = {}
            for g_idx, tdata in enumerate(all_timetables):
                rows = tdata['timetable']
                if row_idx < len(rows) and col_idx < len(rows[row_idx]):
                    cell = rows[row_idx][col_idx]
                    if cell and str(cell).strip().upper() not in ("FREE", "BREAK"):
                        room = _extract_room(cell)
                        course, faculty = _extract_course_and_faculty(cell)
                        if room:
                            room_key = str(room).strip().upper()
                            info = room_usage.setdefault(room_key, {"users": [], "display": room})
                            info["users"].append(g_idx)
                        if faculty and faculty.strip().upper() != 'UNKNOWN':
                            lec_key = faculty.strip().upper()
                            info = lecturer_usage.setdefault(lec_key, {"users": [], "display": faculty})
                            info["users"].append(g_idx)
            # room conflicts
            for r_key, info in room_usage.items():
                users = info.get("users", [])
                if len(users) > 1 and current_group_idx in users:
                    conflicts[key] = {'type': 'room', 'resource': info.get("display", r_key)}
            # lecturer conflicts
            for l_key, info in lecturer_usage.items():
                users = info.get("users", [])
                if len(users) > 1 and current_group_idx in users:
                    if key in conflicts:
                        conflicts[key]['type'] = 'both'
                        conflicts[key]['lecturer'] = info.get("display", l_key)
                    else:
                        conflicts[key] = {'type': 'lecturer', 'resource': info.get("display", l_key)}
    return conflicts


# --- OG-compatible helper wrappers/names ---
extract_room_from_cell = _extract_room
extract_course_and_faculty_from_cell = _extract_course_and_faculty

def extract_course_code_from_cell(cell_content):
    if not cell_content or cell_content in ["FREE", "BREAK"]:
        return None
    lines = str(cell_content).split('\n')
    return lines[0].strip() if lines and lines[0].strip() else None

def update_room_in_cell_content(cell_content, new_room):
    if not cell_content or cell_content in ["FREE", "BREAK"]:
        return cell_content
    lines = str(cell_content).split('\n')
    if len(lines) >= 3:
        lines[1] = new_room
        return '\n'.join(lines)
    elif len(lines) == 2:
        return f"{lines[0]}\n{new_room}\n{lines[1]}"
    elif len(lines) == 1:
        return f"{lines[0]}\n{new_room}\nUnknown"
    return cell_content

def update_consecutive_course_rooms(timetables_data, group_idx, course_code, new_room, current_row, current_col):
    rows = timetables_data[group_idx]['timetable']
    for r in range(len(rows)):
        if r == current_row:
            continue
        cell = rows[r][current_col + 1]
        if extract_course_code_from_cell(cell) == course_code:
            rows[r][current_col + 1] = update_room_in_cell_content(cell, new_room)

def get_room_usage_at_timeslot(all_timetables_data, row_idx, col_idx):
    usage = {}
    for t in all_timetables_data or []:
        rows = t.get('timetable', [])
        if row_idx < len(rows) and (col_idx + 1) < len(rows[row_idx]):
            cell = rows[row_idx][col_idx + 1]
            room = extract_room_from_cell(cell)
            if room:
                name = t['student_group']['name'] if isinstance(t['student_group'], dict) else getattr(t['student_group'], 'name', str(t['student_group']))
                usage.setdefault(room, []).append(name)
    return usage

def save_timetable_to_file(timetables_data, manual_cells_data):
    try:
        save_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(save_dir, exist_ok=True)
        session_path = os.path.join(save_dir, 'timetable_data.json')
        export_path = os.path.join(save_dir, 'fresh_timetable_data.json')
        backup_path = os.path.join(save_dir, 'timetable_data_backup.json')
        if os.path.exists(session_path):
            shutil.copy2(session_path, backup_path)
        data = {'timetables': timetables_data, 'manual_cells': manual_cells_data or []}
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(timetables_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error auto-saving timetable: {e}")
        traceback.print_exc()
        return False

def recompute_constraint_violations_simplified(timetables_data, rooms_data=None):
    try:
        violations = {
            'Same Student Group Overlaps': [],
            'Different Student Group Overlaps': [],
            'Lecturer Clashes': [],
            'Lecturer Schedule Conflicts (Day/Time)': [],
            'Lecturer Workload Violations': [],
            'Consecutive Slot Violations': [],
            'Missing or Extra Classes': [],
            'Same Course in Multiple Rooms on Same Day': [],
            'Room Capacity/Type Conflicts': [],
            'Classes During Break Time': []
        }
        room_lookup = {r['name']: r for r in (rooms_data or [])}
        days_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri'}
        # simple pass through time/day grid
        for time_slot in range(8):
            for day in range(5):
                room_usage = {}
                lecturer_usage = {}
                for timetable in timetables_data or []:
                    if time_slot < len(timetable.get('timetable', [])) and (day + 1) < len(timetable['timetable'][time_slot]):
                        cell = timetable['timetable'][time_slot][day + 1]
                        if cell and cell not in ['FREE', 'BREAK']:
                            lines = str(cell).split('\n')
                            course_code = lines[0].strip() if lines else ''
                            room = lines[1].strip() if len(lines) > 1 else ''
                            lecturer = lines[2].strip() if len(lines) > 2 else 'Unknown'
                            group_name = timetable['student_group']['name'] if isinstance(timetable['student_group'], dict) else getattr(timetable['student_group'], 'name', '')
                            room_usage.setdefault(room, []).append(group_name)
                            if lecturer and lecturer != 'Unknown':
                                lecturer_usage.setdefault(lecturer, []).append({'group': group_name, 'course': course_code})
                            if room in room_lookup:
                                cap = room_lookup[room].get('capacity', 999999)
                                # no_students only available if input_data is present; skip otherwise
                                if input_data is not None:
                                    grp = next((g for g in input_data.student_groups if getattr(g, 'name', '') == group_name), None)
                                    if grp and getattr(grp, 'no_students', 0) > cap:
                                        violations['Room Capacity/Type Conflicts'].append({'type': 'Room Capacity Exceeded', 'room': room, 'group': group_name, 'day': days_map.get(day), 'time': f"{time_slot+9}:00", 'students': getattr(grp, 'no_students', 0), 'capacity': cap})
                for room, groups in room_usage.items():
                    if room and len(groups) > 1:
                        violations['Different Student Group Overlaps'].append({'room': room, 'groups': groups, 'day': days_map.get(day), 'time': f"{time_slot+9}:00", 'location': f"{days_map.get(day)} at {time_slot+9}:00"})
                for lecturer, sessions in lecturer_usage.items():
                    if len(sessions) > 1:
                        violations['Lecturer Clashes'].append({'lecturer': lecturer, 'day': days_map.get(day), 'time': f"{time_slot+9}:00", 'courses': [s['course'] for s in sessions], 'groups': [s['group'] for s in sessions], 'location': f"{days_map.get(day)} at {time_slot+9}:00"})
        return violations
    except Exception as e:
        print(f"Error computing simplified violations: {e}")
        return None


def _make_excel_bytes(all_timetables):
    """Create an in-memory XLSX with one sheet per student group."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for t in all_timetables or []:
        name = t['student_group']['name'] if isinstance(t['student_group'], dict) else str(t['student_group'])
        safe_name = (name or 'Group')[:31]
        ws = wb.create_sheet(title=safe_name)
        for row in t.get('timetable', []):
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def create_errors_modal_content(constraint_details, expanded_constraint=None, toggle_constraint=None):
    if not constraint_details:
        return [html.Div("No constraint violation data available.", style={"padding": "20px", "textAlign": "center"})]
    if not hasattr(create_errors_modal_content, 'expanded_states'):
        create_errors_modal_content.expanded_states = set()
    if toggle_constraint:
        if toggle_constraint in create_errors_modal_content.expanded_states:
            create_errors_modal_content.expanded_states.remove(toggle_constraint)
        else:
            create_errors_modal_content.expanded_states.add(toggle_constraint)
    if expanded_constraint:
        create_errors_modal_content.expanded_states.add(expanded_constraint)
    mapping = {
        'Same Student Group Overlaps': 'Same Student Group Overlaps',
        'Different Student Group Overlaps': 'Different Student Group Overlaps',
        'Lecturer Clashes': 'Lecturer Clashes',
        'Lecturer Schedule Conflicts (Day/Time)': 'Lecturer Schedule Conflicts (Day/Time)',
        'Lecturer Workload Violations': 'Lecturer Workload Violations',
        'Consecutive Slot Violations': 'Consecutive Slot Violations',
        'Missing or Extra Classes': 'Missing or Extra Classes',
        'Same Course in Multiple Rooms on Same Day': 'Same Course in Multiple Rooms on Same Day',
        'Room Capacity/Type Conflicts': 'Room Capacity/Type Conflicts',
        'Classes During Break Time': 'Classes During Break Time'
    }
    content = []
    for display_name, internal_name in mapping.items():
        items = constraint_details.get(internal_name, []) if isinstance(constraint_details, dict) else []
        count = len(items)
        is_expanded = display_name in create_errors_modal_content.expanded_states
        count_class = "constraint-count zero" if count == 0 else "constraint-count non-zero"
        header = html.Div([
            html.Span(display_name, style={"flex": "1"}),
            html.Span(f"{count} Occurrence{'s' if count != 1 else ''}", className=count_class),
            html.Span("^", className=f"constraint-arrow{' rotated' if is_expanded else ''}")
        ], className=f"constraint-header{' active' if is_expanded else ''}", id={"type": "constraint-header", "index": display_name}, n_clicks=0)
        details_content = []
        if items:
            for v in items:
                if internal_name == 'Different Student Group Overlaps':
                    if isinstance(v, dict) and 'groups' in v:
                        details_content.append(html.Div(f"Room conflict in {v.get('room','?')} at {v.get('location','?')}: Groups {', '.join(v.get('groups',[]))} both scheduled", className="constraint-item"))
                    else:
                        details_content.append(html.Div(f"Room conflict at {v.get('location','Unknown')}", className="constraint-item"))
                elif internal_name == 'Lecturer Clashes':
                    if isinstance(v, dict) and 'groups' in v and len(v['groups']) >= 2:
                        details_content.append(html.Div(f"Lecturer '{v.get('lecturer','?')}' has clashing courses {v.get('courses',["?"])[0]} for group {v['groups'][0]}, and {v.get('courses',["?","?"])[1]} for group {v['groups'][1]} on {v.get('location','?')}", className="constraint-item"))
                    else:
                        details_content.append(html.Div(f"Lecturer '{v.get('lecturer','?')}' has clashing courses {', '.join(v.get('courses',[]))} on {v.get('location','?')}", className="constraint-item"))
                else:
                    details_content.append(html.Div(json.dumps(v), className="constraint-item"))
        else:
            details_content.append(html.Div("No violations found.", className="constraint-item", style={"color": "#28a745", "fontStyle": "italic"}))
        content.append(html.Div([
            header,
            html.Div(details_content, className=f"constraint-details{' expanded' if is_expanded else ''}", id={"type": "constraint-details", "index": display_name})
        ], className="constraint-dropdown"))
    return content


def create_app(_ctx: dict | None = None):
    timetables, manual_cells = _load_saved_timetable()
    rooms_data = _load_rooms_data()

    # global-like state for this app instance
    session_state = {'has_swaps': False}

    # compute initial constraints like OG (simplified)
    initial_constraints = recompute_constraint_violations_simplified(timetables, rooms_data) or {}

    app = dash.Dash(__name__)

    # Use OG index_string CSS
    app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {
                font-family: 'Poppins', sans-serif;
            }
            .cell {
                padding: 12px 10px;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                cursor: grab;
                min-height: 45px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 400;
                font-size: 12px;
                transition: all 0.2s ease;
                user-select: none;
                line-height: 1.2;
                text-align: center;
                background-color: white;
                white-space: pre-line;
                word-wrap: break-word;
                overflow-wrap: break-word;
            }
            .cell:hover { transform: translateY(-1px); box-shadow: 0 2px 6px rgba(0,0,0,0.1); border-color: #ccc; }
            .cell.dragging { opacity: 0.6; transform: rotate(2deg); cursor: grabbing; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
            .cell.drag-over { background-color: #fff3cd !important; border-color: #ffc107 !important; transform: scale(1.02); box-shadow: 0 2px 8px rgba(255, 193, 7, 0.6); }
            .cell.break-time { background-color: #ff5722 !important; color: white; cursor: not-allowed; font-weight: 500; }
            .cell.break-time:hover { transform: none; box-shadow: none; }
            .cell.room-conflict { background-color: #ffebee !important; color: #d32f2f !important; border-color: #f44336 !important; font-weight: 600 !important; }
            .cell.room-conflict:hover { background-color: #ffcdd2 !important; box-shadow: 0 2px 8px rgba(244, 67, 54, 0.4); }
            .cell.lecturer-conflict { background-color: #fff0cc !important; color: #d4942f !important; border-color: #d4942f !important; font-weight: 600 !important; }
            .cell.lecturer-conflict:hover { background-color: #fff8e8 !important; box-shadow: 0 2px 8px rgba(244, 67, 54, 0.4); }
            .cell.both-conflict { background-color: #ffdcec !important; color: #d42fa2 !important; border-color: #d42fa2 !important; font-weight: 600 !important; }
            .cell.both-conflict:hover { background-color: #ffdcec !important; box-shadow: 0 2px 8px rgba(244, 67, 54, 0.4); }
            .cell.manual-schedule { border: 3px solid #72B7F4 !important; box-shadow: 0 0 8px rgba(33, 150, 243, 0.4) !important; background-color: #e3f2fd !important; position: relative; }
            .cell.manual-schedule:hover { box-shadow: 0 2px 12px rgba(33, 150, 243, 0.7) !important; border-color: #1976d2 !important; transform: translateY(-1px); }
            .cell.manual-schedule.room-conflict { background-color: #ffebee !important; border: 3px solid #72B7F4 !important; box-shadow: 0 0 8px rgba(33, 150, 243, 0.5) !important; }
            .cell.manual-schedule.lecturer-conflict { background-color: #fff0cc !important; border: 3px solid #72B7F4 !important; box-shadow: 0 0 8px rgba(33, 150, 243, 0.5) !important; }
            .cell.manual-schedule.both-conflict { background-color: #ffebee !important; border: 3px solid #72B7F4 !important; box-shadow: 0 0 8px rgba(33, 150, 243, 0.5) !important; }
            .room-selection-modal { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; border-radius: 12px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2); padding: 25px; z-index: 1000; max-width: 800px; width: 95%; max-height: 80vh; overflow-y: auto; font-family: 'Poppins', sans-serif; }
            .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.5); z-index: 999; }
            .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid #f0f0f0; }
            .modal-title { font-size: 18px; font-weight: 600; color: #11214D; margin: 0; }
            .modal-close { background: none; border: none; font-size: 24px; color: #666; cursor: pointer; padding: 5px; border-radius: 50%; transition: all 0.2s ease; }
            .modal-close:hover { background-color: #f5f5f5; color: #333; }
            .room-search { width: calc(100% - 32px); padding: 12px 16px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 14px; margin-bottom: 15px; transition: border-color 0.2s ease; box-sizing: border-box; }
            .room-search:focus { outline: none; border-color: #11214D; }
            .room-options { max-height: 300px; overflow-y: auto; border: 1px solid #e0e0e0; border-radius: 8px; background: white; }
            .room-option { padding: 12px 16px; border-bottom: 1px solid #f0f0f0; cursor: pointer; transition: background-color 0.2s ease; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
            .room-option:last-child { border-bottom: none; }
            .room-option:hover { background-color: #f8f9fa; }
            .room-option.available { color: #2e7d32; font-weight: 500; }
            .room-option.occupied { color: #d32f2f; font-weight: 500; }
            .room-option.selected { background-color: #e3f2fd; border-left: 4px solid #11214D; }
            .room-info { font-size: 11px; color: #666; }
            .conflict-warning { position: fixed; top: 20px; left: 20px; background: #ffebee; border: 2px solid #f44336; border-radius: 8px; padding: 15px; max-width: 350px; z-index: 1001; box-shadow: 0 4px 12px rgba(244, 67, 54, 0.3); }
            .conflict-warning-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
            .conflict-warning-title { font-weight: 600; color: #d32f2f; font-size: 14px; }
            .conflict-warning-close { background: none; border: none; font-size: 18px; color: #d32f2f; cursor: pointer; padding: 2px; }
            .conflict-warning-content { color: #b71c1c; font-size: 12px; line-height: 1.4; }
            .student-group-container { margin-bottom: 30px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background-color: #fafafa; box-shadow: 0 2px 4px rgba(0,0,0,0.05); max-width: 1200px; margin: 0 auto 30px auto; }
            .dropdown-container { max-width: 1200px; margin: 0 auto; padding: 0 15px; }
            table { font-family: 'Poppins', sans-serif; font-size: 12px; border-collapse: separate; border-spacing: 0; width: 100%; background-color: white; border-radius: 6px; overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
            th { background-color: #11214D !important; color: white !important; padding: 12px 10px !important; font-size: 13px !important; font-weight: 600 !important; text-align: center !important; border: 1px solid #0d1a3d !important; }
            td { padding: 0 !important; border: 1px solid #e0e0e0 !important; background-color: white; }
            .time-cell { background-color: #11214D !important; color: white !important; padding: 12px 10px !important; font-weight: 600 !important; text-align: center !important; font-size: 12px !important; border: 1px solid #0d1a3d !important; }
            .timetable-title { color: #11214D; font-weight: 600; margin-bottom: 20px; font-size: 20px; }
            .timetable-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 0 10px; }
            .nav-arrows { display: flex; align-items: center; gap: 15px; }
            .nav-arrow { background: #11214D; color: white; border: none; border-radius: 15%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 16px; font-weight: bold; transition: all 0.2s ease; }
            .nav-arrow:hover { background: #0d1a3d; transform: scale(1.05); box-shadow: 0 2px 8px rgba(17, 33, 77, 0.3); }
            .nav-arrow:disabled { background: #ccc; cursor: not-allowed; transform: none; box-shadow: none; }
            .save-error { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: #ffebee; border: 2px solid #f44336; border-radius: 8px; padding: 15px 20px; max-width: 400px; z-index: 1001; text-align: center; }
            .save-error-title { font-weight: 600; color: #d32f2f; font-size: 14px; margin-bottom: 8px; }
            .save-error-content { color: #b71c1c; font-size: 12px; line-height: 1.4; }
            .constraint-dropdown { margin-bottom: 15px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
            .constraint-header { background-color: #f8f9fa; padding: 12px 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 14px; color: #11214D; border-bottom: 1px solid #e0e0e0; gap: 15px; }
            .constraint-details { padding: 0; max-height: 0; overflow: hidden; transition: max-height 0.3s ease-out; background: white; }
            .constraint-details.expanded { max-height: 300px; overflow-y: auto; border-top: 1px solid #e0e0e0; }
            .errors-button { position: relative; background: #dc3545; color: white; border: none; border-radius: 8px; padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer; box-shadow: 0 2px 4px rgba(220, 53, 69, 0.3); }
            .error-notification { position: absolute; top: -8px; right: -8px; background: rgba(255, 255, 255, 0.9); color: #dc3545; border: 2px solid #dc3545; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
            .help-modal { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; border-radius: 12px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2); padding: 30px; z-index: 1000; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; font-family: 'Poppins', sans-serif; }
            .help-modal h3 { color: #11214D; font-weight: 600; margin-bottom: 20px; font-size: 20px; text-align: center; }
            .help-section { margin-bottom: 20px; }
            .help-section h4 { color: #11214D; font-weight: 600; margin-bottom: 10px; font-size: 16px; }
            .help-section p { color: #555; line-height: 1.6; margin-bottom: 10px; font-size: 14px; }
            .help-note { background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 15px; margin-bottom: 20px; color: #856404; font-weight: 500; }
            .color-legend { display: flex; flex-direction: column; gap: 8px; }
            .color-item { display: flex; align-items: center; gap: 10px; }
            .color-box { width: 20px; height: 20px; border-radius: 4px; border: 1px solid #ccc; }
            .color-box.manual { background-color: #72b7f4; }
            .color-box.normal { background-color: white; }
            .color-box.break { background-color: #ff5722; }
            .color-box.room-conflict { background-color: #ffebee; border-color: #f44336; }
            .color-box.lecturer-conflict { background-color: #ffd982; border-color: #d4942f; }
            .color-box.both-conflict { background-color: #ffdcec; border-color: #d42fa2; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

    # Dropdown options from timetables
    options = [
        {'label': (t['student_group']['name'] if isinstance(t['student_group'], dict) else str(t['student_group'])), 'value': idx}
        for idx, t in enumerate(timetables)
    ]

    # Layout: match OG exactly - title and dropdown on same line
    app.layout = html.Div([
        # Title and dropdown on the same line
        html.Div([
            html.H1("Interactive Drag & Drop Timetable - DE Optimization Results", 
                    style={"color": "#11214D", "fontWeight": "600", "fontSize": "24px", 
                          "fontFamily": "Poppins, sans-serif", "margin": "0", "flex": "1"}),
            
            html.Div([
                dcc.Dropdown(id='student-group-dropdown', options=options, value=0, searchable=True, clearable=False, style={"width": "280px", "fontSize": "13px", "fontFamily": "Poppins, sans-serif"})
            ], style={"display": "flex", "alignItems": "center"})
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", 
                 "marginTop": "30px", "marginBottom": "30px", "maxWidth": "1200px", 
                 "margin": "30px auto", "padding": "0 15px"}),

        dcc.Store(id='all-timetables-store', data=timetables),
        dcc.Store(id='rooms-data-store', data=rooms_data),
        dcc.Store(id='original-timetables-store', data=[json.loads(json.dumps(t)) for t in timetables]),
        dcc.Store(id='constraint-details-store', data=initial_constraints),
        dcc.Store(id='swap-data', data=None),
        dcc.Store(id='room-change-data', data=None),
        dcc.Store(id='missing-class-data', data=None),
        dcc.Store(id='manual-cells-store', data=manual_cells or []),

        html.Div(id='trigger', style={'display': 'none'}),
        html.Div(id='timetable-container'),

        # Room selection modal
        html.Div([
            html.Div(className='modal-overlay', id='modal-overlay', style={'display': 'none'}),
            html.Div([
                html.Div([html.H3('Select Classroom', className='modal-title'), html.Button('×', className='modal-close', id='modal-close-btn')], className='modal-header'),
                dcc.Input(id='room-search-input', type='text', placeholder='Search classrooms...', className='room-search'),
                html.Div(id='room-options-container', className='room-options'),
                html.Div([
                    html.Button('Cancel', id='room-cancel-btn', style={"backgroundColor": "#f5f5f5", "color": "#666", "padding": "8px 16px", "border": "1px solid #ddd", "borderRadius": "5px", "marginRight": "10px", "cursor": "pointer"}),
                    html.Button('DELETE SCHEDULE', id='room-delete-btn', style={"backgroundColor": "#dc3545", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer", "marginRight": "10px", "fontWeight": "600", "display": "none"}),
                    html.Button('Confirm', id='room-confirm-btn', style={"backgroundColor": "#11214D", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer"})
                ], style={"textAlign": "right", "marginTop": "20px", "paddingTop": "15px", "borderTop": "1px solid #f0f0f0"})
            ], className='room-selection-modal', id='room-selection-modal', style={'display': 'none'})
        ], style={"position": "relative"}),

        # Missing classes modal
        html.Div([
            html.Div(className='modal-overlay', id='missing-modal-overlay', style={'display': 'none'}),
            html.Div([
                html.Div([html.H3('Missing Classes', className='modal-title'), html.Button('×', className='modal-close', id='missing-modal-close-btn')], className='modal-header'),
                html.Div(id='missing-classes-container', className='room-options'),
                html.Div([html.Button('Cancel', id='missing-cancel-btn', style={"backgroundColor": "#f5f5f5", "color": "#666", "padding": "8px 16px", "border": "1px solid #ddd", "borderRadius": "5px", "cursor": "pointer"})], style={"textAlign": "right", "marginTop": "20px", "paddingTop": "15px", "borderTop": "1px solid #f0f0f0"})
            ], className='room-selection-modal', id='missing-classes-modal', style={'display': 'none'})
        ], style={"position": "relative"}),

        # Errors modal
        html.Div([
            html.Div(className='modal-overlay', id='errors-modal-overlay', style={'display': 'none'}),
            html.Div([
                html.Div([html.H3('Constraint Violations', className='modal-title'), html.Button('×', className='modal-close', id='errors-modal-close-btn')], className='modal-header'),
                html.Div(id='errors-content'),
                html.Div([html.Button('Close', id='errors-close-btn', style={"backgroundColor": "#11214D", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer"})], style={"textAlign": "right", "marginTop": "20px", "paddingTop": "15px", "borderTop": "1px solid #f0f0f0"})
            ], className='room-selection-modal', id='errors-modal', style={'display': 'none'})
        ]),

        # Download modal
        html.Div([
            html.Div(className='modal-overlay', id='download-modal-overlay', style={'display': 'none'}),
            html.Div([
                html.Div([html.H3('Download Timetables', className='modal-title'), html.Button('×', className='modal-close', id='download-modal-close-btn')], className='modal-header'),
                html.Div([
                    html.Div([html.Span('Download SST Timetables', style={"flex": "1", "fontSize": "16px", "fontWeight": "500"}), html.Button('Download', id='download-sst-btn', style={"backgroundColor": "#11214D", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer", "fontSize": "14px"})], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "padding": "15px", "borderBottom": "1px solid #f0f0f0"}),
                    html.Div([html.Span('Download TYD Timetables', style={"flex": "1", "fontSize": "16px", "fontWeight": "500"}), html.Button('Download', id='download-tyd-btn', style={"backgroundColor": "#11214D", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer", "fontSize": "14px"})], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "padding": "15px", "borderBottom": "1px solid #f0f0f0"}),
                    html.Div([html.Span('Download all Lecturer Timetables', style={"flex": "1", "fontSize": "16px", "fontWeight": "500"}), html.Button('Download', id='download-lecturer-btn', style={"backgroundColor": "#11214D", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer", "fontSize": "14px"})], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "padding": "15px"})
                ]),
                html.Div([html.Button('Close', id='download-close-btn', style={"backgroundColor": "#6c757d", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer"})], style={"textAlign": "right", "marginTop": "20px", "paddingTop": "15px", "borderTop": "1px solid #f0f0f0"})
            ], className='room-selection-modal', id='download-modal', style={'display': 'none'})
        ]),

        # Conflict warning and save error popups
        html.Div([html.Div([html.Span('⚠️ Classroom Conflict', className='conflict-warning-title'), html.Button('×', className='conflict-warning-close', id='conflict-close-btn')], className='conflict-warning-header'), html.Div(id='conflict-warning-text', className='conflict-warning-content')], className='conflict-warning', id='conflict-warning', style={'display': 'none'}),
        html.Div([html.Div('❌ Cannot Save Timetable', className='save-error-title'), html.Div('Please resolve all classroom conflicts before saving the timetable.', className='save-error-content')], className='save-error', id='save-error', style={'display': 'none'}),

        # Bottom controls: download button and status
        html.Div([
            html.Button('Download Timetables', id='download-button', style={"backgroundColor": "#11214D", "color": "white", "padding": "10px 20px", "border": "none", "borderRadius": "5px", "fontSize": "14px", "cursor": "pointer", "fontWeight": "600", "boxShadow": "0 1px 3px rgba(0,0,0,0.1)", "transition": "all 0.2s ease"}),
            html.Div(id='download-status', style={"marginTop": "12px", "fontWeight": "600", "fontSize": "12px"})
        ], style={"textAlign": "center", "marginTop": "30px", "maxWidth": "1200px", "margin": "30px auto 0 auto"}),

        # Add Download component for client-side downloads
        dcc.Download(id='download-data'),

        html.Div(id='feedback', style={"marginTop": "20px", "textAlign": "center", "fontSize": "16px", "fontWeight": "bold", "minHeight": "30px", "maxWidth": "1200px", "margin": "20px auto 0 auto"}),

        # Help modal
        html.Div([
            html.Div(className='modal-overlay', id='help-modal-overlay', style={'display': 'none'}),
            html.Div([
                html.Div([
                    html.H3('Timetable Help Guide', className='modal-title'),
                    html.Button('×', className='modal-close', id='help-modal-close-btn')
                ], className='modal-header'),
                
                html.Div([
                    html.Div([
                        html.Strong('NOTE: '),
                        'Ensure all Lecturer names, emails and other details are inputted correctly to prevent errors'
                    ], className='help-note'),
                    
                    html.Div([
                        html.H4('How to Use the Timetable:'),
                        html.P('• Click and drag any class cell to swap it with another cell'),
                        html.P('• Double-click any cell to view and change the classroom for that class'),
                        html.P('• Use the navigation arrows (‹ ›) to switch between different student groups'),
                        html.P("• Click 'View Errors' to see constraint violations and conflicts")
                    ], className='help-section'),
                    
                    html.Div([
                        html.H4('Cell Color Meanings:'),
                        html.Div([
                            html.Div([
                                html.Div(className='color-box normal'),
                                html.Span('Normal class - No conflicts')
                            ], className='color-item'),
                            html.Div([
                                html.Div(className='color-box manual'),
                                html.Span("Manually Scheduled - Class scheduled manually from the 'Missing Classes' list.")
                            ], className='color-item'),
                            html.Div([
                                html.Div(className='color-box break'),
                                html.Span('Break time - Classes cannot be scheduled')
                            ], className='color-item'),
                            html.Div([
                                html.Div(className='color-box room-conflict'),
                                html.Span('Room conflict - Same classroom used by multiple groups')
                            ], className='color-item'),
                            html.Div([
                                html.Div(className='color-box lecturer-conflict'),
                                html.Span('Lecturer conflict - Same lecturer teaching multiple groups')
                            ], className='color-item'),
                            html.Div([
                                html.Div(className='color-box both-conflict'),
                                html.Span('Multiple conflicts - Both room and lecturer issues')
                            ], className='color-item')
                        ], className='color-legend')
                    ], className='help-section')
                ]),
                
                html.Div([
                    html.Button('Close', id='help-close-btn', style={
                        "backgroundColor": "#11214D", "color": "white", "padding": "10px 20px",
                        "border": "none", "borderRadius": "8px", "cursor": "pointer",
                        "fontFamily": "Poppins, sans-serif", "fontSize": "14px", "fontWeight": "600"
                    })
                ], style={"textAlign": "center", "marginTop": "25px", "paddingTop": "20px", 
                         "borderTop": "2px solid #f0f0f0"})
            ], className='help-modal', id='help-modal', style={'display': 'none'})
        ])
    ])

    # Create timetable for selected group (matches OG: returns children and trigger)
    @app.callback(
        [Output('timetable-container', 'children'), Output('trigger', 'children')],
        [Input('student-group-dropdown', 'value')],
        [State('all-timetables-store', 'data'), State('manual-cells-store', 'data')]
    )
    def create_timetable(selected_group_idx, all_timetables_data, manual_cells_state):
        if selected_group_idx is None or not all_timetables_data:
            return html.Div('No data available'), 'trigger'
        if selected_group_idx >= len(all_timetables_data):
            selected_group_idx = 0
        tdata = all_timetables_data[selected_group_idx]
        name = tdata['student_group']['name'] if isinstance(tdata['student_group'], dict) else getattr(tdata['student_group'], 'name', str(tdata['student_group']))
        rows = tdata['timetable']
        conflicts = _detect_conflicts(all_timetables_data, selected_group_idx)
        header_cells = [html.Th('Time', style={"backgroundColor": "#11214D", "color": "white", "padding": "12px 10px", "fontWeight": "600", "fontSize": "13px", "textAlign": "center", "border": "1px solid #0d1a3d"})]
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            header_cells.append(html.Th(day, style={"backgroundColor": "#11214D", "color": "white", "padding": "12px 10px", "fontWeight": "600", "fontSize": "13px", "textAlign": "center", "border": "1px solid #0d1a3d"}))
        body_rows = []
        for r in range(len(rows)):
            cells = [html.Td(rows[r][0], className='time-cell')]
            for c in range(1, len(rows[r])):
                raw = rows[r][c] if rows[r][c] else 'FREE'
                text = str(raw).strip()
                text_upper = text.upper()
                is_break = text_upper == 'BREAK'
                key = f"{r}_{c-1}"
                ctype = conflicts.get(key, {}).get('type', 'none') if key in conflicts else 'none'
                manual_key = f"{selected_group_idx}_{r}_{c-1}"
                is_manual = bool(manual_cells_state) and manual_key in (manual_cells_state or [])
                if is_break:
                    cls = 'cell break-time'; draggable = 'false'
                elif is_manual:
                    cls = 'cell manual-schedule'
                    if ctype == 'room': cls = 'cell room-conflict manual-schedule'
                    if ctype == 'lecturer': cls = 'cell lecturer-conflict manual-schedule'
                    if ctype == 'both': cls = 'cell both-conflict manual-schedule'
                    draggable = 'true'
                else:
                    cls_map = {'room': 'cell room-conflict', 'lecturer': 'cell lecturer-conflict', 'both': 'cell both-conflict'}
                    cls = cls_map.get(ctype, 'cell'); draggable = 'true'
                cell_id = {"type": "cell", "group": selected_group_idx, "row": r, "col": c-1}
                cells.append(html.Td(html.Div(text, id=cell_id, className=cls, draggable=draggable, n_clicks=0), style={"padding": "0", "border": "1px solid #e0e0e0"}))
            body_rows.append(html.Tr(cells))
        table = html.Table([html.Thead(html.Tr(header_cells)), html.Tbody(body_rows)], style={"width": "100%", "borderCollapse": "separate", "borderSpacing": "0", "backgroundColor": "white", "borderRadius": "6px", "overflow": "hidden", "fontSize": "12px", "boxShadow": "0 2px 6px rgba(0,0,0,0.08)", "fontFamily": "Poppins, sans-serif"})
        # Header with title and navigation arrows
        header = html.Div([
            html.Div([
                html.H2(f"Timetable for {name}", className='timetable-title', style={"color": "#11214D", "fontWeight": "600", "fontSize": "20px", "fontFamily": "Poppins, sans-serif", "margin": "0"})
            ], className='timetable-title-container'),
            html.Div([
                html.Button('‹', className='nav-arrow', id='prev-group-btn', disabled=selected_group_idx == 0),
                html.Button('›', className='nav-arrow', id='next-group-btn', disabled=selected_group_idx == len(all_timetables_data) - 1)
            ], className='nav-arrows')
        ], className='timetable-header')
        # Buttons row with Help button aligned to the right
        btns = html.Div([
            html.Button(['View Errors', html.Div(id='error-notification-badge', className='error-notification')], id='errors-btn', className='errors-button'),
            html.Button('Undo All Changes', id='undo-all-btn', style={"backgroundColor": "#6c757d", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "fontSize": "14px", "cursor": "pointer", "fontWeight": "500", "fontFamily": "Poppins, sans-serif"}),
            html.Button('?', id='help-icon-btn', title='Help', className='nav-arrow', style={"marginLeft": "auto"})
        ], style={"marginBottom": "15px", "marginRight": "10px", "textAlign": "left", "display": "flex", "gap": "10px", "alignItems": "flex-start"})
        return html.Div([header, btns, table], className='student-group-container'), 'trigger'

    # Update timetable content after swaps
    @app.callback(
        Output('timetable-container', 'children', allow_duplicate=True),
        Input('all-timetables-store', 'data'),
        [State('student-group-dropdown', 'value'), State('manual-cells-store', 'data')],
        prevent_initial_call=True
    )
    def update_timetable_content(all_timetables_data, selected_group_idx, manual_cells_state):
        if selected_group_idx is None or not all_timetables_data or selected_group_idx >= len(all_timetables_data):
            raise dash.exceptions.PreventUpdate
        # reuse create_timetable body to render container only
        children, _ = create_timetable(selected_group_idx, all_timetables_data, manual_cells_state)
        return children

    # Navigation arrows
    @app.callback(
        Output('student-group-dropdown', 'value'),
        [Input('prev-group-btn', 'n_clicks'), Input('next-group-btn', 'n_clicks')],
        [State('student-group-dropdown', 'value'), State('all-timetables-store', 'data')],
        prevent_initial_call=True
    )
    def handle_navigation(prev_clicks, next_clicks, current_value, all_timetables_data):
        ctx = dash.callback_context
        if not ctx.triggered or not all_timetables_data:
            raise dash.exceptions.PreventUpdate
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        click_value = ctx.triggered[0]['value']
        if click_value is None or click_value == 0:
            raise dash.exceptions.PreventUpdate
        if current_value is None:
            current_value = 0
        max_index = len(all_timetables_data) - 1
        current_value = max(0, min(current_value, max_index))
        if button_id == 'prev-group-btn' and current_value > 0:
            return current_value - 1
        if button_id == 'next-group-btn' and current_value < max_index:
            return current_value + 1
        raise dash.exceptions.PreventUpdate

    # Drag/drop and dblclick clientside setup (from OG, condensed)
    clientside_callback(
        """
        function(trigger){
            window.draggedElement=null; window.dragStartData=null; window.selectedCell=null;
            function setup(){
                const cells=document.querySelectorAll('.cell');
                cells.forEach(function(cell){
                    cell.ondblclick=function(e){ e.preventDefault(); e.stopPropagation();
                        if(this.textContent.trim()==='FREE'){
                            window.selectedCell=this; const m=document.getElementById('missing-classes-modal'); const o=document.getElementById('missing-modal-overlay'); if(m&&o){m.style.display='block'; o.style.display='block';}
                            if(window.dash_clientside&&window.dash_clientside.set_props){ window.dash_clientside.set_props('missing-class-data',{data:{action:'show_missing',cell_id:this.id,timestamp:Date.now()}});} return; }
                        if(this.classList.contains('break-time')||this.textContent.trim()==='BREAK') return;
                        window.selectedCell=this; const m=document.getElementById('room-selection-modal'); const o=document.getElementById('modal-overlay'); const d=document.getElementById('room-delete-btn'); if(m&&o){m.style.display='block'; o.style.display='block';}
                        if(d){ d.style.display=this.classList.contains('manual-schedule')?'inline-block':'none'; }
                        if(window.dash_clientside&&window.dash_clientside.set_props){ window.dash_clientside.set_props('room-change-data',{ data:{ action:'show_modal', cell_id:this.id, cell_content:this.textContent.trim(), is_manual:this.classList.contains('manual-schedule'), timestamp:Date.now() }}); }
                        setTimeout(function(){ const s=document.getElementById('room-search-input'); if(s) s.focus(); },100);
                    };
                    cell.ondragstart=function(e){ if(this.classList.contains('break-time')||this.textContent.trim()==='BREAK'){ e.preventDefault(); return false; }
                        window.draggedElement=this; try{ const obj=JSON.parse(this.id); window.dragStartData={group:obj.group,row:obj.row,col:obj.col,content:this.textContent.trim(),cellId:this.id}; }catch(_){ window.draggedElement=null; window.dragStartData=null; return false; } this.classList.add('dragging'); e.dataTransfer.effectAllowed='move'; e.dataTransfer.setData('text/html', this.id); };
                    cell.ondragover=function(e){ e.preventDefault(); e.dataTransfer.dropEffect='move'; };
                    cell.ondragenter=function(e){ e.preventDefault(); if(this!==window.draggedElement&&!this.classList.contains('break-time')&&this.textContent.trim()!=='BREAK'){ this.classList.add('drag-over'); }};
                    cell.ondragleave=function(e){ this.classList.remove('drag-over'); };
                    cell.ondrop=function(e){ e.preventDefault(); e.stopPropagation(); if(this.classList.contains('break-time')||this.textContent.trim()==='BREAK'){ this.classList.remove('drag-over'); return false; }
                        if(!window.draggedElement||!window.dragStartData){ this.classList.remove('drag-over'); return false; } if(this===window.draggedElement){ this.classList.remove('drag-over'); return false; } if(window.draggedElement.id!==window.dragStartData.cellId){ this.classList.remove('drag-over'); return false; }
                        try{ const targetObj=JSON.parse(this.id); const target={group:targetObj.group,row:targetObj.row,col:targetObj.col,content:this.textContent.trim(),cellId:this.id}; if(window.dragStartData.group!==target.group){ this.classList.remove('drag-over'); return false; }
                            const sourceIsManual=window.draggedElement.classList.contains('manual-schedule'); const targetIsManual=this.classList.contains('manual-schedule');
                            const tmp=window.draggedElement.textContent; window.draggedElement.textContent=this.textContent; this.textContent=tmp;
                            if(sourceIsManual){ this.classList.add('manual-schedule'); window.draggedElement.classList.remove('manual-schedule'); }
                            if(targetIsManual){ window.draggedElement.classList.add('manual-schedule'); this.classList.remove('manual-schedule'); }
                            if(window.dash_clientside&&window.dash_clientside.set_props){ window.dash_clientside.set_props('swap-data',{data:{source:window.dragStartData,target:target,sourceIsManual:sourceIsManual,targetIsManual:targetIsManual,timestamp:Date.now()}}); }
                            const fb=document.getElementById('feedback'); if(fb){ fb.innerHTML='✅ Swapped'; fb.style.color='green'; fb.style.backgroundColor='#e8f5e8'; fb.style.padding='10px'; fb.style.borderRadius='5px'; fb.style.border='2px solid #4caf50'; }
                            window.draggedElement=null; window.dragStartData=null; } catch(err){}
                        this.classList.remove('drag-over'); return false; };
                    cell.ondragend=function(e){ this.classList.remove('dragging'); document.querySelectorAll('.cell').forEach(function(c){ c.classList.remove('drag-over','dragging'); }); window.draggedElement=null; window.dragStartData=null; };
                });
            }
            function setupModalHandlers(){ const close=function(){ const m=document.getElementById('room-selection-modal'); const o=document.getElementById('modal-overlay'); if(m&&o){ m.style.display='none'; o.style.display='none'; } window.selectedCell=null; }; const x=document.getElementById('modal-close-btn'); const c=document.getElementById('room-cancel-btn'); const o=document.getElementById('modal-overlay'); if(x) x.onclick=close; if(c) c.onclick=close; if(o) o.onclick=close; }
            setTimeout(function(){ setup(); setupModalHandlers(); },100);
            let to=null; const obs=new MutationObserver(function(m){ let s=false; m.forEach(function(mu){ if(mu.type==='childList'&&mu.addedNodes.length>0){ for(let i=0;i<mu.addedNodes.length;i++){ const n=mu.addedNodes[i]; if(n.nodeType===1 && (n.classList && n.classList.contains('cell') || (n.querySelector && n.querySelector('.cell')))){ s=true; break; } } } }); if(s){ if(to) clearTimeout(to); to=setTimeout(function(){ if(!window.draggedElement && !window.dragStartData){ setup(); setupModalHandlers(); } to=null; },150); } }); const cont=document.getElementById('timetable-container'); if(cont){ obs.observe(cont,{childList:true,subtree:true}); }
            return window.dash_clientside.no_update;
        }
        """,
        Output('feedback', 'style'),
        Input('trigger', 'children'),
        prevent_initial_call=False
    )

    # Room modal options + visibility
    @app.callback(
        [Output('room-options-container', 'children'), Output('room-selection-modal', 'style'), Output('modal-overlay', 'style'), Output('room-delete-btn', 'style')],
        [Input('room-change-data', 'data'), Input('room-search-input', 'value')],
        [State('all-timetables-store', 'data'), State('rooms-data-store', 'data'), State('student-group-dropdown', 'value'), State('manual-cells-store', 'data')],
        prevent_initial_call=True
    )
    def handle_room_modal(room_change_data, search_value, all_timetables_data, rooms, selected_group_idx, manual_cells_state):
        if not room_change_data or room_change_data.get('action') != 'show_modal':
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        if not rooms or not all_timetables_data:
            return html.Div('No rooms data available'), {"display": "block"}, {"display": "block"}, {"display": "none"}
        try:
            cell_id = json.loads(room_change_data['cell_id'])
            row_idx, col_idx, group_idx = cell_id['row'], cell_id['col'], cell_id['group']
        except Exception:
            return html.Div('Error parsing cell data'), {"display": "block"}, {"display": "block"}, {"display": "none"}
        current_usage = get_room_usage_at_timeslot(all_timetables_data, row_idx, col_idx)
        filtered = rooms
        if search_value:
            s = str(search_value).lower()
            filtered = [r for r in rooms if s in str(r.get('name','')).lower() or s in str(r.get('building','')).lower() or s in str(r.get('room_type','')).lower()]
        opts = []
        for room in filtered:
            name = room.get('name')
            is_available = name not in current_usage
            info = '' if is_available else f" (Used by: {', '.join(current_usage[name])})"
            option_class = 'room-option available' if is_available else 'room-option occupied'
            opts.append(html.Div([
                html.Div([html.Span(name, style={"fontWeight": "600"}), html.Span(info, style={"fontSize": "11px", "color": "#666", "marginLeft": "8px"})], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"}),
                html.Div([html.Span(f"Cap: {room.get('capacity','?')}", className='room-info'), html.Span(f" | {room.get('building','')}", className='room-info'), html.Span(f" | {room.get('room_type','N/A')}", className='room-info')])
            ], className=option_class, id={"type": "room-option", "room_id": room.get('Id'), "room_name": name}, n_clicks=0))
        manual_key = f"{group_idx}_{row_idx}_{col_idx}"
        delete_style = {"backgroundColor": "#dc3545", "color": "white", "padding": "8px 16px", "border": "none", "borderRadius": "5px", "cursor": "pointer", "marginRight": "10px", "fontWeight": "600", "display": "inline-block" if (manual_cells_state and manual_key in (manual_cells_state or [])) else "none"}
        return opts, {"display": "block"}, {"display": "block"}, delete_style

    # Handle room list click to set selected room in store
    @app.callback(
        Output('room-change-data', 'data', allow_duplicate=True),
        [Input({'type': 'room-option', 'room_id': dash.dependencies.ALL, 'room_name': dash.dependencies.ALL}, 'n_clicks')],
        [State({'type': 'room-option', 'room_id': dash.dependencies.ALL, 'room_name': dash.dependencies.ALL}, 'id'), State('room-change-data', 'data'), State('all-timetables-store', 'data')],
        prevent_initial_call=True
    )
    def handle_room_selection(n_clicks_list, room_ids, current_room_data, all_timetables_data):
        if not any(n_clicks_list) or not current_room_data:
            return dash.no_update
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update
        try:
            triggered_room = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
            selected_room_name = triggered_room['room_name']
        except Exception:
            return dash.no_update
        return {**current_room_data, 'action': 'room_selected', 'selected_room': selected_room_name, 'timestamp': (current_room_data.get('timestamp', 0) if isinstance(current_room_data, dict) else 0) + 1}

    # Confirm room change or delete manual schedule
    @app.callback(
        [Output('all-timetables-store', 'data', allow_duplicate=True), Output('manual-cells-store', 'data', allow_duplicate=True), Output('conflict-warning', 'style'), Output('conflict-warning-text', 'children')],
        [Input('room-confirm-btn', 'n_clicks'), Input('room-delete-btn', 'n_clicks')],
        [State('room-change-data', 'data'), State('all-timetables-store', 'data'), State('student-group-dropdown', 'value'), State('rooms-data-store', 'data'), State('manual-cells-store', 'data')],
        prevent_initial_call=True
    )
    def confirm_room_change(confirm_clicks, delete_clicks, room_change_data, all_timetables_data, selected_group_idx, rooms, manual_cells_state):
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        updated_manual = manual_cells_state.copy() if manual_cells_state else []
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        # Delete manual
        if trigger_id == 'room-delete-btn' and delete_clicks:
            if not room_change_data:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
            try:
                cid = json.loads(room_change_data['cell_id']); r = cid['row']; c = cid['col']; g = cid['group']
                updated = json.loads(json.dumps(all_timetables_data))
                updated[g]['timetable'][r][c+1] = 'FREE'
                key = f"{g}_{r}_{c}"
                if key in updated_manual:
                    updated_manual.remove(key)
                save_timetable_to_file(updated, updated_manual)
                return updated, updated_manual, {"display": "none"}, ''
            except Exception as e:
                return dash.no_update, dash.no_update, {"display": "block"}, f"Error deleting schedule: {str(e)}"
        # Confirm room
        if trigger_id == 'room-confirm-btn' and confirm_clicks:
            if not room_change_data or room_change_data.get('action') != 'room_selected':
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
            session_state['has_swaps'] = True
            try:
                cid = json.loads(room_change_data['cell_id']); r = cid['row']; c = cid['col']
                selected_room = room_change_data['selected_room']
                updated = json.loads(json.dumps(all_timetables_data))
                cur = updated[selected_group_idx]['timetable']
                original = cur[r][c+1]
                cur[r][c+1] = update_room_in_cell_content(original, selected_room)
                course_code = extract_course_code_from_cell(original)
                if course_code:
                    update_consecutive_course_rooms(updated, selected_group_idx, course_code, selected_room, r, c)
                usage = get_room_usage_at_timeslot(updated, r, c)
                warn_style = {"display": "none"}; warn_text = ''
                if selected_room in usage and len(usage[selected_room]) > 1:
                    others = [g for g in usage[selected_room] if g != (updated[selected_group_idx]['student_group']['name'])]
                    warn_style = {"display": "block"}; warn_text = f"This classroom is already in use by: {', '.join(others)}"
                save_timetable_to_file(updated, updated_manual)
                return updated, manual_cells_state, warn_style, warn_text
            except Exception as e:
                return dash.no_update, dash.no_update, {"display": "block"}, f"Error updating room: {str(e)}"
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # Handle swaps: update data and manual cell states, auto-save
    @app.callback(
        [Output('all-timetables-store', 'data', allow_duplicate=True), Output('manual-cells-store', 'data', allow_duplicate=True)],
        Input('swap-data', 'data'),
        [State('all-timetables-store', 'data'), State('manual-cells-store', 'data')],
        prevent_initial_call=True
    )
    def handle_swap(swap_data, current_timetables, manual_cells_state):
        if not swap_data or not current_timetables:
            raise dash.exceptions.PreventUpdate
        try:
            source = swap_data['source']; target = swap_data['target']
            if source['group'] != target['group']:
                raise dash.exceptions.PreventUpdate
            if source.get('content') == 'BREAK' or target.get('content') == 'BREAK':
                raise dash.exceptions.PreventUpdate
            g = source['group']
            updated = json.loads(json.dumps(current_timetables))
            rows = updated[g]['timetable']
            if (source['row'] >= len(rows) or target['row'] >= len(rows) or source['col'] + 1 >= len(rows[0]) or target['col'] + 1 >= len(rows[0])):
                raise dash.exceptions.PreventUpdate
            s_content = rows[source['row']][source['col'] + 1]
            t_content = rows[target['row']][target['col'] + 1]
            rows[source['row']][source['col'] + 1] = t_content
            rows[target['row']][target['col'] + 1] = s_content
            session_state['has_swaps'] = True
            source_is_manual = swap_data.get('sourceIsManual', False)
            target_is_manual = swap_data.get('targetIsManual', False)
            updated_manual = manual_cells_state.copy() if manual_cells_state else []
            s_key = f"{g}_{source['row']}_{source['col']}"; t_key = f"{g}_{target['row']}_{target['col']}"
            if source_is_manual and s_key in updated_manual: updated_manual.remove(s_key)
            if target_is_manual and t_key in updated_manual: updated_manual.remove(t_key)
            if source_is_manual and t_key not in updated_manual: updated_manual.append(t_key)
            if target_is_manual and s_key not in updated_manual: updated_manual.append(s_key)
            save_timetable_to_file(updated, updated_manual)
            return updated, updated_manual
        except Exception as e:
            traceback.print_exc()
            raise dash.exceptions.PreventUpdate

    # Update constraint violations after user changes
    @app.callback(
        Output('constraint-details-store', 'data', allow_duplicate=True),
        [Input('all-timetables-store', 'data')],
        [State('rooms-data-store', 'data'), State('constraint-details-store', 'data')],
        prevent_initial_call=True
    )
    def update_constraints_rt(timetables_data, rooms, current_constraints):
        if not timetables_data:
            return dash.no_update
        if not session_state['has_swaps']:
            return dash.no_update
        updated = recompute_constraint_violations_simplified(timetables_data, rooms)
        return updated or current_constraints

    # Errors modal open/close and content
    @app.callback(
        [Output('errors-modal-overlay', 'style'), Output('errors-modal', 'style'), Output('errors-content', 'children')],
        [Input('errors-btn', 'n_clicks'), Input('errors-modal-close-btn', 'n_clicks'), Input('errors-close-btn', 'n_clicks'), Input('errors-modal-overlay', 'n_clicks')],
        State('constraint-details-store', 'data'),
        prevent_initial_call=True
    )
    def handle_errors_modal(errors_btn_clicks, close1, close2, overlay, constraint_details):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'errors-btn' and errors_btn_clicks:
            content = create_errors_modal_content(constraint_details)
            return {"display": "block"}, {"display": "block"}, content
        if trigger_id in ['errors-modal-close-btn', 'errors-close-btn', 'errors-modal-overlay']:
            return {"display": "none"}, {"display": "none"}, []
        raise dash.exceptions.PreventUpdate

    # Toggle constraint dropdown
    @app.callback(
        Output('errors-content', 'children', allow_duplicate=True),
        [Input({"type": "constraint-header", "index": dash.dependencies.ALL}, 'n_clicks')],
        [State('constraint-details-store', 'data'), State('errors-content', 'children')],
        prevent_initial_call=True
    )
    def toggle_constraint_dropdown(n_clicks_list, constraint_details, current_content):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n_clicks_list or []):
            raise dash.exceptions.PreventUpdate
        try:
            clicked_id = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
            clicked = clicked_id.get('index')
        except Exception:
            raise dash.exceptions.PreventUpdate
        return create_errors_modal_content(constraint_details, toggle_constraint=clicked)

    # Error badge count (sum of hard-constraint occurrences like OG badge)
    @app.callback(
        Output('error-notification-badge', 'children'),
        [Input('constraint-details-store', 'data'), Input('all-timetables-store', 'data')],
        prevent_initial_call=False
    )
    def update_error_badge(constraint_details, timetables_data):
        if not isinstance(constraint_details, dict):
            return '0'
        hard = ['Same Student Group Overlaps','Different Student Group Overlaps','Lecturer Clashes','Lecturer Schedule Conflicts (Day/Time)','Lecturer Workload Violations','Consecutive Slot Violations','Missing or Extra Classes','Same Course in Multiple Rooms on Same Day','Room Capacity/Type Conflicts','Classes During Break Time']
        n = sum(len(constraint_details.get(k, [])) for k in hard)
        return str(n)

    # Missing classes modal open/populate (basic placeholder using constraints store)
    @app.callback(
        [Output('missing-classes-container', 'children'), Output('missing-classes-modal', 'style'), Output('missing-modal-overlay', 'style')],
        [Input('missing-class-data', 'data')],
        [State('constraint-details-store', 'data'), State('student-group-dropdown', 'value'), State('all-timetables-store', 'data')],
        prevent_initial_call=True
    )
    def handle_missing_classes_modal(missing_data, constraint_details, selected_group_idx, all_timetables_data):
        if not missing_data or missing_data.get('action') != 'show_missing':
            return dash.no_update, dash.no_update, dash.no_update
        # Simplified: show placeholder if no constraint data
        if not constraint_details:
            return html.Div('No constraint data available'), {"display": "block"}, {"display": "block"}
        return [html.Div('Select a class to schedule (placeholder)', className='room-option available', id={"type": "missing-class-option", "index": 0, "course": "MANUAL-CLASS", "faculty": "Unknown"}, n_clicks=0)], {"display": "block"}, {"display": "block"}

    # Close help/download modals
    @app.callback(
        [Output('help-modal-overlay', 'style'), Output('help-modal', 'style')],
        [Input('help-icon-btn', 'n_clicks'), Input('help-modal-close-btn', 'n_clicks'), Input('help-close-btn', 'n_clicks'), Input('help-modal-overlay', 'n_clicks')],
        prevent_initial_call=True
    )
    def handle_help_modal(help_btn_clicks, close1, close2, overlay):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'help-icon-btn' and help_btn_clicks:
            return {"display": "block"}, {"display": "block"}
        if trigger_id in ['help-modal-close-btn', 'help-close-btn', 'help-modal-overlay']:
            return {"display": "none"}, {"display": "none"}
        raise dash.exceptions.PreventUpdate

    @app.callback(
        [Output('download-modal-overlay', 'style'), Output('download-modal', 'style')],
        [Input('download-button', 'n_clicks'), Input('download-modal-close-btn', 'n_clicks'), Input('download-close-btn', 'n_clicks'), Input('download-modal-overlay', 'n_clicks')],
        prevent_initial_call=True
    )
    def handle_download_modal(download_btn_clicks, close1, close2, overlay):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'download-button' and download_btn_clicks:
            return {"display": "block"}, {"display": "block"}
        if trigger_id in ['download-modal-close-btn', 'download-close-btn', 'download-modal-overlay']:
            return {"display": "none"}, {"display": "none"}
        raise dash.exceptions.PreventUpdate

    # Replace download handler to send files to browser (no server-side save)
    @app.callback(
        [Output('download-status', 'children'), Output('download-data', 'data')],
        [Input('download-sst-btn', 'n_clicks'), Input('download-tyd-btn', 'n_clicks'), Input('download-lecturer-btn', 'n_clicks')],
        prevent_initial_call=True
    )
    def handle_download_actions(sst_clicks, tyd_clicks, lecturer_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        try:
            # Build workbooks in-memory using exporter helpers
            from output_data import TimetableExporter
            from openpyxl import Workbook
            import re
            from datetime import datetime as _dt

            exporter = TimetableExporter()
            data = exporter.get_timetable_data()
            if not data:
                return html.Div('❌ No timetable data available', style={"color": "red", "fontWeight": "600"}), dash.no_update

            def wb_to_bytes(wb):
                buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf.getvalue()

            if trigger_id == 'download-sst-btn' and sst_clicks:
                from collections import defaultdict
                sst_programs = defaultdict(list)
                for group_data in data:
                    group_name = group_data['student_group']['name']
                    if exporter.is_sst_group(group_name):
                        main_program = exporter.extract_main_program_name(group_name)
                        sst_programs[main_program].append(group_data)
                if not sst_programs:
                    return html.Div('❌ No SST groups found', style={"color": "red", "fontWeight": "600"}), dash.no_update
                wb = Workbook(); wb.remove(wb.active)
                for program_name, groups in sst_programs.items():
                    groups.sort(key=lambda x: x['student_group']['name'])
                    safe_sheet_name = re.sub(r'[^\w\s-]', '', program_name)[:31]
                    exporter.create_combined_program_sheet(wb, safe_sheet_name, groups)
                bytes_xlsx = wb_to_bytes(wb)
                ts = _dt.now().strftime('%Y%m%d_%H%M%S')
                filename = f"SST_Timetables_{ts}.xlsx"
                return html.Div('✅ SST export ready', style={"color": "green", "fontWeight": "600"}), dcc.send_bytes(lambda b: b.write(bytes_xlsx), filename)

            if trigger_id == 'download-tyd-btn' and tyd_clicks:
                from collections import defaultdict
                tyd_programs = defaultdict(list)
                for group_data in data:
                    group_name = group_data['student_group']['name']
                    if not exporter.is_sst_group(group_name):
                        main_program = exporter.extract_main_program_name(group_name)
                        tyd_programs[main_program].append(group_data)
                if not tyd_programs:
                    return html.Div('❌ No TYD groups found', style={"color": "red", "fontWeight": "600"}), dash.no_update
                wb = Workbook(); wb.remove(wb.active)
                for program_name, groups in tyd_programs.items():
                    groups.sort(key=lambda x: x['student_group']['name'])
                    safe_sheet_name = re.sub(r'[^\w\s-]', '', program_name)[:31]
                    exporter.create_combined_program_sheet(wb, safe_sheet_name, groups)
                bytes_xlsx = wb_to_bytes(wb)
                ts = _dt.now().strftime('%Y%m%d_%H%M%S')
                filename = f"TYD_Timetables_{ts}.xlsx"
                return html.Div('✅ TYD export ready', style={"color": "green", "fontWeight": "600"}), dcc.send_bytes(lambda b: b.write(bytes_xlsx), filename)

            if trigger_id == 'download-lecturer-btn' and lecturer_clicks:
                from collections import defaultdict
                lecturer_schedules = defaultdict(list)
                for group_data in data:
                    student_group_name = group_data['student_group']['name']
                    timetable_rows = group_data['timetable']
                    for time_slot_idx, row_data in enumerate(timetable_rows):
                        for day_idx in range(len(exporter.days)):
                            if day_idx + 1 < len(row_data):
                                cell_content = row_data[day_idx + 1]
                                info = exporter.extract_lecturer_info(cell_content)
                                if info and info['course_code']:
                                    course_code = info['course_code']
                                    course_info = exporter.course_data.get(course_code, {})
                                    faculty_ids = course_info.get('facultyId', [])
                                    if isinstance(faculty_ids, str):
                                        faculty_ids = [faculty_ids]
                                    for faculty_id in faculty_ids:
                                        faculty_info = exporter.faculty_data.get(faculty_id, {})
                                        lecturer_name = faculty_info.get('name', faculty_id)
                                        if lecturer_name and lecturer_name.lower() not in ['unknown', 'tbd', 'staff', '']:
                                            lecturer_schedules[lecturer_name].append({
                                                'time_slot': time_slot_idx,
                                                'day': day_idx,
                                                'course_code': course_code,
                                                'room': info['room'],
                                                'student_group': student_group_name
                                            })
                if not lecturer_schedules:
                    return html.Div('❌ No lecturer data found', style={"color": "red", "fontWeight": "600"}), dash.no_update
                wb = Workbook(); wb.remove(wb.active)
                exporter.create_combined_lecturer_sheet(wb, "Lecturer Timetables", lecturer_schedules)
                bytes_xlsx = wb_to_bytes(wb)
                ts = _dt.now().strftime('%Y%m%d_%H%M%S')
                filename = f"Lecturer_Timetables_{ts}.xlsx"
                return html.Div('✅ Lecturer export ready', style={"color": "green", "fontWeight": "600"}), dcc.send_bytes(lambda b: b.write(bytes_xlsx), filename)

        except Exception as e:
            return html.Div(f"❌ Error: {str(e)}", style={"color": "red", "fontWeight": "600"}), dash.no_update

    # Undo all changes
    @app.callback(
        [Output('all-timetables-store', 'data', allow_duplicate=True), Output('feedback', 'children', allow_duplicate=True)],
        Input('undo-all-btn', 'n_clicks'),
        State('original-timetables-store', 'data'),
        prevent_initial_call=True
    )
    def handle_undo_all_changes(n_clicks, original_timetables):
        if n_clicks and original_timetables:
            # Clear saved session so fresh results are used on restart
            try:
                save_dir = os.path.join(os.path.dirname(__file__), 'data')
                for p in ['timetable_data.json', 'timetable_data_backup.json']:
                    f = os.path.join(save_dir, p)
                    if os.path.exists(f):
                        os.remove(f)
            except Exception:
                pass
            return original_timetables, html.Div('✅ All changes have been undone!', style={"color": "green", "fontWeight": "600"})
        raise dash.exceptions.PreventUpdate

    # Safeguard dropdown validity
    @app.callback(
        Output('student-group-dropdown', 'value', allow_duplicate=True),
        Input('student-group-dropdown', 'value'),
        State('all-timetables-store', 'data'),
        prevent_initial_call=True
    )
    def validate_dropdown_selection(selected_value, all_timetables_data):
        if not all_timetables_data or selected_value is None:
            return 0
        max_index = len(all_timetables_data) - 1
        if selected_value < 0 or selected_value > max_index:
            return 0
        raise dash.exceptions.PreventUpdate

    # Simple client handlers
    clientside_callback(
        """
        function(children){ if(!children) return window.dash_clientside.no_update; setTimeout(function(){ const opts=document.querySelectorAll('.room-option'); opts.forEach(function(o){ o.onclick=function(){ opts.forEach(function(x){ x.classList.remove('selected'); }); this.classList.add('selected'); }; }); },100); return window.dash_clientside.no_update; }
        """,
        Output('room-options-container', 'style'),
        Input('room-options-container', 'children'),
        prevent_initial_call=True
    )

    clientside_callback(
        """
        function(n){ if(n){ const m=document.getElementById('room-selection-modal'); const o=document.getElementById('modal-overlay'); if(m&&o){ m.style.display='none'; o.style.display='none'; } const fb=document.getElementById('feedback'); if(fb){ fb.innerHTML='✅ Classroom updated successfully'; fb.style.color='green'; fb.style.backgroundColor='#e8f5e8'; fb.style.padding='10px'; fb.style.borderRadius='5px'; fb.style.border='2px solid #4caf50'; } } return window.dash_clientside.no_update;
        }""",
        Output('room-confirm-btn', 'style'),
        Input('room-confirm-btn', 'n_clicks'),
        prevent_initial_call=True
    )

    clientside_callback(
        """
        function(style){ if(style && style.display==='block'){ setTimeout(function(){ const e=document.getElementById('save-error'); if(e){ e.style.display='none'; } },4000); } return window.dash_clientside.no_update; }
        """,
        Output('save-error', 'children'),
        Input('save-error', 'style'),
        prevent_initial_call=True
    )

    clientside_callback(
        """
        function(n){ if(n){ const m=document.getElementById('missing-classes-modal'); const o=document.getElementById('missing-modal-overlay'); if(m&&o){ m.style.display='none'; o.style.display='none'; } } return window.dash_clientside.no_update; }
        """,
        Output('missing-cancel-btn', 'style'),
        Input('missing-cancel-btn', 'n_clicks'),
        prevent_initial_call=True
    )

    # Close conflict warning on × click
    clientside_callback(
        """
        function(n){ if(n){ const cw=document.getElementById('conflict-warning'); if(cw){ cw.style.display='none'; } } return window.dash_clientside.no_update; }
        """,
        Output('conflict-close-btn', 'style'),
        Input('conflict-close-btn', 'n_clicks'),
        prevent_initial_call=True
    )

    return app
