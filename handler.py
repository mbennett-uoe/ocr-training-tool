from flask import Flask, render_template, request, url_for, redirect, flash, abort
from forms import LoginForm, is_safe_url, Stage1Form, stage2form_factory, Stage3Form
from flask_login import login_user, LoginManager, login_required, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = r'sqlite:///./ocr.db'
app.secret_key = b'changeme'

bcrypt = Bcrypt(app)
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), unique=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    current_page = db.Column(db.String(16))
    current_stage = db.Column(db.Integer)

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __repr__(self):
        return '<User %r>' % self.username

    def get_id(self):
        return unicode(self.id)

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def get_current(self):
        if self.current_page:
            return self.current_page, self.current_stage
        else:
            return None

    def set_current(self, page, stage=None):
        self.current_page = page
        self.current_stage = stage


class Page(db.Model):
    id = db.Column(db.String(16), primary_key=True)
    shelfmark = db.Column(db.String(128), nullable=False)
    document = db.Column(db.String(8), nullable=False)
    sequence = db.Column(db.String(8), nullable=False)
    page_type = db.Column(db.String(16))
    handwriting = db.Column(db.Boolean)
    bad_crop = db.Column(db.Boolean)
    page_issue = db.Column(db.Boolean)
    issue_description = db.Column(db.Text)
    is_finished = db.Column(db.Boolean, default=False, nullable=False)
    lines = db.relationship('Line', backref='page', lazy=True)

    @property
    def has_issue(self):
        return self.handwriting or self.bad_crop or self.page_issue or False

    @property
    def dirpath(self):
        return "%s/%s/%s" % (self.shelfmark, self.document, self.sequence)

    def __repr__(self):
        return '<Page %r>' % self.id


class Line(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey('page.id'), nullable=False)
    position = db.Column(db.Integer)
    not_found = db.Column(db.Boolean, default=False)
    is_marginalia = db.Column(db.Boolean, default=False)
    ocr = db.Column(db.String(256))
    corrected = db.Column(db.String(256))

    @property
    def has_changes(self):
        return not(self.ocr == self.corrected)

    def __repr__(self):
        return '<Page %r Line %r>' % (self.page.id, self.position)


@app.route('/')
@login_required
def index():
    stats = {"Pages": Page.query.count(),
             "Lines": Line.query.count(),
             "Finished": Page.query.filter_by(is_finished=True).count(),
             }
    current = current_user.get_current()
    return render_template("index.html", stats=stats, current=current)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm(request.form)
    if request.method == "POST":
        # Login and validate the user.
        # user should be an instance of your `User` class
        user = User.query.filter_by(username=form.username.data).first()
        if user.check_password(form.password.data):
            login_user(user)
            flash('Logged in successfully.')
            next_url = form.next.data
            # is_safe_url should check if the url is safe for redirects.
            # See http://flask.pocoo.org/snippets/62/ for an example.
            if not is_safe_url(next_url):
                return abort(400)

            return redirect(next_url or url_for('index'))
        else:
            flash('Incorrect username or password.', "Error")
    return render_template('login.html', form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return "Logged out"


@app.route("/view/<page_id>")
@login_required
def view(page_id):
    page = Page.query.get_or_404(page_id)
    form = Stage3Form(obj=page)
    return render_template("view.html", page=page, form=form)


@app.route("/edit/<page_id>")
@app.route("/edit/<page_id>/stage<int:stage>", methods=['GET', 'POST'])
@login_required
def edit(page_id, stage=None):
    page = Page.query.get_or_404(page_id)
    forms = {1: Stage1Form,
             2: stage2form_factory(page),
             3: Stage3Form}
    current_user.set_current(page_id, stage)
    db.session.commit()
    if stage is None:
        return redirect(url_for('edit', page_id=page_id, stage=1))
    if request.method == "GET":
            other_users = User.query.filter_by(current_page=page_id).filter(User.id != current_user.id).first()
            form = forms[stage](request.form, obj=page)
            return render_template('stage%s.html'%stage, page=page, form=form, other_users=other_users)
    elif request.method == "POST":
        form = forms[stage](request.form)
        if stage == 1:
            form.populate_obj(page)
            db.session.commit()
            return redirect(url_for('edit', page_id=page_id, stage=2))
        elif stage == 2:
            for line in page.lines:
                line.corrected = getattr(form, "line-%s"%line.position).data
                line.is_marginalia = getattr(form, "line-%s-m" % line.position).data
                line.not_found = getattr(form, "line-%s-n" % line.position).data
            db.session.commit()
            if form.save.data:
                return redirect(url_for('edit', page_id=page_id, stage=2))
            else:
                return redirect(url_for('edit', page_id=page_id, stage=3))
        elif stage == 3:
            if form.finalise.data:
                page.is_finished = True
                current_user.set_current(None, None)
                db.session.commit()
                flash("Record saved")
                return redirect(url_for('index'))
            if form.stage1.data:
                return redirect(url_for('edit', page_id=page_id, stage=1))
            if form.stage2.data:
                return redirect(url_for('edit', page_id=page_id, stage=2))


@app.route("/getpage", methods=['GET', 'POST'])
@login_required
def get_page():
    page = Page.query.filter_by(is_finished=False).order_by(func.random()).first()
    if page:
        return redirect(url_for('edit', page_id=page.id, stage=1))
    else:
        return redirect(url_for('index', message="No Pages"))






