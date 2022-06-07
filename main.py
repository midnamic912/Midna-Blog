import smtplib

from flask import Flask, render_template, redirect, url_for, flash, abort, request
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
from flask_gravatar import Gravatar
from functools import wraps
from dotenv import load_dotenv
from os import getenv


load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = getenv("SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap(app)

##CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = getenv("POSTGRESQL_URL", "sqlite:///blog.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


##CONFIGURE TABLES

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    name = db.Column(db.String(250), nullable=False)

    # this is not a column but an attribute of the class
    # indicates that the value of this attribute will be a list of BlogPost objects.
    # the 'back_populates' tells this attribute is related to 'author' attribute in other class.
    # that allows if there is a configuration in 'posts', there will also be one in 'author'
    # and we can tab into them both to get data like User.posts and BlogPost.author
    posts = relationship("BlogPost", back_populates="author")

    comments = relationship("Comment", back_populates="comment_author")


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)
    # line below means this 'author_id' column's value is constrained by the id column of the users table
    # that means a 'author_id' must match one of the 'id' in users table
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # indicate that the value of this column will be an User object.
    # the 'back_populates' tells this author column is related to 'posts' column in other table.
    # if some entries be added/deleted in 'author', there will also be values added/deleted in 'posts' column
    author = relationship("User", back_populates="posts")

    comments = relationship("Comment", back_populates="parent_post")


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)

    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comment_author = relationship("User", back_populates="comments")

    post_id = db.Column(db.Integer, db.ForeignKey('blog_posts.id'))
    parent_post = relationship("BlogPost", back_populates="comments")


# Line below only required once, when creating DB.
db.create_all()

##LOGIN STUFF
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    print(f"current user: {user_id}")
    print("execute callback load_user")
    return User.query.get(int(user_id))  # return a User object or None if no matched user


# Customized View district decorator
def admin_only(func):
    # make the name of function not 'wrapper' but original function name,
    # preventing the endpoint names from being the same and raising an Assertion error
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.get_id() != "1":
            return abort(403)  # return a HTTP Error page made by flask
        return func(*args, **kwargs)

    return wrapper


## Gravatar for users leaving comments
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

@app.route('/')
def get_all_posts():
    posts = BlogPost.query.all()
    user_id = current_user.get_id()
    return render_template("index.html", all_posts=posts, logged_in=current_user.is_authenticated, user_id=user_id)


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if not form.validate_on_submit():
        return render_template("register.html", form=form)

    # if user already exist
    if User.query.filter_by(email=form.data.get("email")).first():
        flash("You've already signed up with the email. Login instead!")
        return redirect(url_for('login'))

    # hash and salt the password that user entered
    password = form.data.get("password")
    hashed_password = generate_password_hash(password=password, method="pbkdf2:sha256", salt_length=8)

    new_user = User(
        email=form.data.get("email"),
        password=hashed_password,
        name=form.data.get("name"),
    )

    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for('get_all_posts'))


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if not form.validate_on_submit():
        return render_template("login.html", form=form)

    user = User.query.filter_by(email=form.email.data).first()

    if not user:
        flash("Sorry, the email doesn't exist. Please try again.")
        return redirect(url_for('login'))

    if not check_password_hash(pwhash=user.password, password=form.password.data):
        flash('Wrong Password.')
        return redirect(url_for('login'))

    login_user(user)
    return redirect(url_for('get_all_posts'))


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    requested_post = BlogPost.query.get(post_id)
    if not form.validate_on_submit():
        return render_template("post.html", post=requested_post, form=form, logged_in=current_user.is_authenticated,
                               user_id=current_user.get_id())

    if not current_user.is_authenticated:
        flash("Sorry, you have to login to make a comment. Login or Register now!")
        return redirect(url_for('login'))

    new_comment = Comment(
        text=form.comment.data,
        # just add relational attributes which are already connected when creating tables.
        # Then the 'author_id' and 'post_id' columns will be filled up automatically.
        comment_author=current_user,
        parent_post=requested_post,
    )
    db.session.add(new_comment)
    db.session.commit()
    return redirect(url_for('show_post', post_id=requested_post.id))


@app.route("/about")
def about():
    return render_template("about.html", logged_in=current_user.is_authenticated)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":  # request.method gets the method type of the HTTP request
        name = request.form["name"]  # request.form gets the form data transmitted by the HTTP request in dict format
        email = request.form["email"]
        phone = request.form["phone"]
        message = request.form["message"]
        with smtplib.SMTP("smtp.gmail.com") as connection:
            connection.starttls()
            connection.login(user=getenv("MY_EMAIL"), password=getenv("MY_PW"))
            connection.sendmail(from_addr=getenv("MY_EMAIL"), to_addrs="midnamic912@gmail.com",
                                msg=f"Subject: New Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nMessage: {message}")
    return render_template("contact.html", method=request.method, logged_in=current_user.is_authenticated)


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,  # must be a User object (constrained above by relationship())
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = BlogPost.query.get(post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,  # a User object
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))

    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = BlogPost.query.get(post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


if __name__ == "__main__":
    app.run(debug=True)
