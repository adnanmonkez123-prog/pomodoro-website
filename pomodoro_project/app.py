from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pomodoro-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pomodoro.db'
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- نموذج قاعدة البيانات ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='student')
    is_banned = db.Column(db.Boolean, default=False)
    
    work_time = db.Column(db.Integer, default=25)
    short_break = db.Column(db.Integer, default=5)
    long_break = db.Column(db.Integer, default=15)

class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- التصميم والواجهات ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>تطبيق Pomodoro الدراسي</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #f4f6f8; margin: 0; padding: 20px; text-align: center; }
        nav { margin-bottom: 20px; }
        a { color: #3498db; text-decoration: none; margin: 0 10px; font-weight: bold; }
        .card { background: white; max-width: 500px; margin: 20px auto; padding: 25px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .timer { font-size: 50px; font-weight: bold; color: #2c3e50; margin: 20px 0; }
        button { background: #3498db; color: white; border: none; padding: 10px 20px; font-size: 16px; border-radius: 6px; cursor: pointer; margin: 5px; }
        button:hover { background: #2980b9; }
        button.danger { background: #e74c3c; }
        input { padding: 10px; margin: 5px; width: 80%; border: 1px solid #ccc; border-radius: 4px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
        th { background: #f2f2f2; }
    </style>
</head>
<body>
    <nav>
        {% if current_user.is_authenticated %}
            أهلاً بك <b>{{ current_user.username }}</b> | 
            {% if current_user.role == 'admin' %}<a href="/admin">لوحة التحكم (المالك)</a> |{% endif %}
            <a href="/logout">تسجيل الخروج</a>
        {% else %}
            <a href="/login">تسجيل الدخول</a> | <a href="/register">حساب جديد</a>
        {% endif %}
    </nav>
    {% with messages = get_flashed_messages() %}
      {% if messages %}<p style="color: red;">{{ messages[0] }}</p>{% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
</body>
</html>
"""

DASHBOARD_HTML = HTML_TEMPLATE + """
{% block content %}
<div class="card">
    <h2>مؤقت Pomodoro</h2>
    <div class="timer" id="timerDisplay">{{ current_user.work_time }}:00</div>
    <div>
        <button onclick="startTimer('work')">دراسة ({{ current_user.work_time }}د)</button>
        <button onclick="startTimer('short')">استراحة قصيرة ({{ current_user.short_break }}د)</button>
        <button onclick="startTimer('long')">استراحة طويلة ({{ current_user.long_break }}د)</button>
    </div>
    <br>
    <button id="actionBtn" onclick="toggleTimer()" style="background:#2ecc71;">إبدأ</button>
    <button onclick="resetTimer()" class="danger">إعادة ضبط</button>
</div>

<div class="card">
    <h3>تعديل مدة التوقيت (بالدقائق)</h3>
    <form method="POST" action="/update_settings">
        <input type="number" name="work" value="{{ current_user.work_time }}" placeholder="وقت الدراسة" required>
        <input type="number" name="short" value="{{ current_user.short_break }}" placeholder="استراحة قصيرة" required>
        <input type="number" name="long" value="{{ current_user.long_break }}" placeholder="استراحة طويلة" required>
        <button type="submit">حفظ الإعدادات</button>
    </form>
</div>

<div class="card">
    <h3>🏆 متصدرين الدراسة (Top 5)</h3>
    <table>
        <tr><th>المركز</th><th>المستخدم</th><th>مجموع الدقائق</th></tr>
        {% for user, total in leaderboard %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ user }}</td>
            <td>{{ total or 0 }} دقيقة</td>
        </tr>
        {% endfor %}
    </table>
</div>

<script>
    let timer;
    let secondsLeft = {{ current_user.work_time }} * 60;
    let isRunning = false;
    let currentType = 'work';
    let currentDuration = {{ current_user.work_time }};

    function updateDisplay() {
        let m = Math.floor(secondsLeft / 60);
        let s = secondsLeft % 60;
        document.getElementById('timerDisplay').innerText = `${m}:${s < 10 ? '0' : ''}${s}`;
    }

    function startTimer(type) {
        clearInterval(timer);
        isRunning = false;
        document.getElementById('actionBtn').innerText = 'إبدأ';
        currentType = type;
        if(type === 'work') currentDuration = {{ current_user.work_time }};
        if(type === 'short') currentDuration = {{ current_user.short_break }};
        if(type === 'long') currentDuration = {{ current_user.long_break }};
        secondsLeft = currentDuration * 60;
        updateDisplay();
    }

    function toggleTimer() {
        if(isRunning) {
            clearInterval(timer);
            document.getElementById('actionBtn').innerText = 'استئناف';
        } else {
            timer = setInterval(() => {
                if(secondsLeft > 0) {
                    secondsLeft--;
                    updateDisplay();
                } else {
                    clearInterval(timer);
                    alert("انتهى الوقت!");
                    if(currentType === 'work') {
                        fetch('/log_session', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({duration: currentDuration})
                        }).then(() => location.reload());
                    }
                }
            }, 1000);
            document.getElementById('actionBtn').innerText = 'إيقاف مؤقت';
        }
        isRunning = !isRunning;
    }

    function resetTimer() { startTimer(currentType); }
</script>
{% endblock %}
"""

LOGIN_HTML = HTML_TEMPLATE + """
{% block content %}
<div class="card">
    <h2>تسجيل الدخول</h2>
    <form method="POST">
        <input type="text" name="username" placeholder="اسم المستخدم" required><br>
        <input type="password" name="password" placeholder="كلمة السر" required><br>
        <button type="submit">دخول</button>
    </form>
</div>
{% endblock %}
"""

REGISTER_HTML = HTML_TEMPLATE + """
{% block content %}
<div class="card">
    <h2>حساب جديد</h2>
    <form method="POST">
        <input type="text" name="username" placeholder="اسم المستخدم" required><br>
        <input type="password" name="password" placeholder="كلمة السر" required><br>
        <button type="submit">تسجيل</button>
    </form>
</div>
{% endblock %}
"""

ADMIN_HTML = HTML_TEMPLATE + """
{% block content %}
<div class="card">
    <h2>لوحة تحكم المالك (Admin)</h2>
    <table>
        <tr><th>المستخدم</th><th>الحالة</th><th>الإجراءات</th></tr>
        {% for user in users %}
        {% if user.id != current_user.id %}
        <tr>
            <td>{{ user.username }}</td>
            <td>{{ 'محظور' if user.is_banned else 'نشط' }}</td>
            <td>
                <a href="/admin/toggle_ban/{{ user.id }}"><button>{{ 'إلغاء الحظر' if user.is_banned else 'حظر' }}</button></a>
                <a href="/admin/delete/{{ user.id }}"><button class="danger">حذف</button></a>
            </td>
        </tr>
        {% endif %}
        {% endfor %}
    </table>
</div>
{% endblock %}
"""

# --- المسارات ---
@app.route('/')
@login_required
def dashboard():
    if current_user.is_banned:
        logout_user()
        flash('حسابك محظور من قبل المالك.')
        return redirect(url_for('login'))
        
    leaderboard = db.session.query(
        User.username, db.func.sum(StudySession.duration_minutes).label('total')
    ).join(StudySession, User.id == StudySession.user_id)\
     .group_by(User.id)\
     .order_by(db.desc('total'))\
     .limit(5).all()

    return render_template_string(DASHBOARD_HTML, leaderboard=leaderboard)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم مستخدم بالفعل.')
            return redirect(url_for('register'))
        
        # أول حساب يسجل يكون هو "المالك" (Admin)
        role = 'admin' if User.query.count() == 0 else 'student'
        new_user = User(
            username=username, 
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template_string(REGISTER_HTML)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            if user.is_banned:
                flash('حسابك محظور من المالك.')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('بيانات الدخول غير صحيحة.')
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    current_user.work_time = int(request.form['work'])
    current_user.short_break = int(request.form['short'])
    current_user.long_break = int(request.form['long'])
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/log_session', methods=['POST'])
@login_required
def log_session():
    data = request.get_json()
    session = StudySession(user_id=current_user.id, duration_minutes=data['duration'])
    db.session.add(session)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        return "غير مسموح", 403
    users = User.query.all()
    return render_template_string(ADMIN_HTML, users=users)

@app.route('/admin/toggle_ban/<int:user_id>')
@login_required
def toggle_ban(user_id):
    if current_user.role != 'admin': return "Forbidden", 403
    user = User.query.get_or_404(user_id)
    user.is_banned = not user.is_banned
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role != 'admin': return "Forbidden", 403
    user = User.query.get_or_404(user_id)
    StudySession.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('admin_panel'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)