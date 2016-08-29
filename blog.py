import hashlib
import hmac
import jinja2
import random
import re
import os
import webapp2
from string import letters
from google.appengine.ext import db

secret = 'vedp09'
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               autoescape=True)


def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)


def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())


def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val


class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    # sets a cookie whose name is name and value is val
    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        # expire time not set so it expires when
        # when you close the browser.
        # set the cookie on Path / so we can delete on same path
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        # find the cookie in the request
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    # sets the cookie using user id and thats how we get the user id in the db
    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    # delete the cookie
    # sets the user cookie if to nothing -> user_id=; we keep the same Path,
    # hence we are overriding the same cookie
    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    # checks to see if the user is logged in or not throughout the blog
    # checks the cookie
    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        # check if cookie 'user_id' exists and if yes, store in
        # self.user
        uid = self.read_secure_cookie('user_id')
        # if user_id is valid it assigns self.user to that user
        self.user = uid and User.by_id(int(uid))


def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)


class MainPage(BlogHandler):
    def get(self):
        self.write('Hello, Udacity!')


# user stuff
def make_salt(length=5):
    return ''.join(random.choice(letters) for x in xrange(length))


# h is what we store in the db
def make_pw_hash(name, pw, salt=None):
    if not salt:
        salt = make_salt()

    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)


# takes name and password and checks if it matches
# the value in the database
def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)


# creates the ancestor element to store all our users
# in our db
def users_key(group='default'):
    return db.Key.from_path('users', group)


# user object that is stored in the db
class User(db.Model):
    name = db.StringProperty(required=True)
    # we dont store pwd in the db, we store the hashed pwd
    pw_hash = db.StringProperty(required=True)
    email = db.StringProperty()
    # Convenience Fxns

    # looks up a user by id
    # you can call this method[by_id] on this object[User]
    # doesn't have to be an instance of the object
    @classmethod
    # cls refers to self, which here is Class User
    def by_id(cls, uid):
        # get_by_id is a Datastore fxn
        return cls.get_by_id(uid, parent=users_key())

    # looks up a user by name
    @classmethod
    def by_name(cls, name):
        # select * from User where name = name
        u = cls.all().filter('name =', name).get()
        return u

    # takes name, pw and email and creates a new User object
    # creates a new User object, but doesn't store in DB
    @classmethod
    def register(cls, name, pw, email=None):
        pw_hash = make_pw_hash(name, pw)
        return cls(parent=users_key(), name=name, pw_hash=pw_hash, email=email)

    # https://www.udacity.com/course/viewer#!/c-cs253/l-48587898/m-48369757
    # returns the user if name and pws is a valid combination and None if not
    # used in class Login
    @classmethod
    def login(cls, name, pw):
        # cls.by_name allows us to overwrite this fxn
        # by_name calls @classmethod by_name, finds user associated by the name
        u = cls.by_name(name)
        # if user exists and the pw is valid
        if u and valid_pw(name, pw, u.pw_hash):
            return u

class Post(db.Model):
    subject = db.StringProperty(required=True)
    content = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    created_by = db.TextProperty()
    likes = db.IntegerProperty(required=True)
    liked_by = db.ListProperty(str)

    @classmethod
    def by_post_name(cls, name):
        # select * from User where name = name
        u = cls.all().filter('name =', name).get()
        return u

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p=self)

    @property
    def comments(self):
        return Comment.all().filter( "post = ", str(self.key().id()) )

class Comment(db.Model):
    comment = db.StringProperty(required=True)
    post = db.StringProperty(required=True)

    @classmethod
    def render(self):
        self.render("comment.html")


# blog stuff

USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
PASS_RE = re.compile(r"^.{3,20}$")
EMAIL_RE = re.compile(r'^[\S]+@[\S]+\.[\S]+$')


def valid_username(username):
    return username and USER_RE.match(username)


def valid_password(password):
    return password and PASS_RE.match(password)


def valid_email(email):
    return not email or EMAIL_RE.match(email)


class Signup(BlogHandler):
    def get(self):
        if not self.user:
            self.render("signup-form.html")
        else:
            log_error = "Logout before to signup"
            self.render('signup-form.html', log_error=log_error)

    def post(self):
        if not self.user:
            have_error = False
            self.username = self.request.get('username')
            self.password = self.request.get('password')
            self.verify = self.request.get('verify')
            self.email = self.request.get('email')

            params = dict(username=self.username, email=self.email)

            if not valid_username(self.username):
                params['error_username'] = "That's not a valid username."
                have_error = True

            if not valid_password(self.password):
                params['error_password'] = "That wasn't a valid password."
                have_error = True
            elif self.password != self.verify:
                params['error_verify'] = "Your passwords didn't match."
                have_error = True

            if not valid_email(self.email):
                params['error_email'] = "That's not a valid email."
                have_error = True

            if have_error:
                self.render('signup-form.html', **params)
            else:
                self.done()
        else:
            log_error = "Logout before to signup"
            self.render('signup-form.html', log_error=log_error)

    def done(self, *a, **kw):
        raise NotImplementedError


# inherits from the Signup class
class Register(Signup):
    # overrites done to handle if the user already exists
    def done(self):
        # make sure the user doesn't already exist
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup-form.html', error_username=msg)
        else:
            # creates a new User object
            u = User.register(self.username, self.password, self.email)
            # store in DB
            print "name ===", self.username
            u.put()

            # set the cookie - from class BlogHandler
            self.login(u)
            self.redirect('/blog')


class Login(BlogHandler):
    def get(self):

        if not self.user:
            self.render('login-form.html')
        else:
            log_error = "You need to log out to login again"
            self.render('login-form.html', log_error=log_error)

    def post(self):
        if not self.user:
            username = self.request.get('username')
            password = self.request.get('password')

            # from @classhandler login, returns the user if (username, password)
            # is a valid combination
            u = User.login(username, password)
            if u:
                # this login is from class BlogHandler which sets the cookie using
                # 'u' which is returned from login(username, password)
                # (used in class Register as well)
                self.login(u)
                self.redirect('/blog')
            else:
                msg = 'Invalid login'
                self.render('login-form.html', error=msg)
        else:
            log_error = "You need to log out to login again"
            self.render('login-form.html', log_error=log_error)


class Logout(BlogHandler):
    def get(self):
        # logout defined in BlogHandler
        if self.user:            
            self.logout()
            self.redirect('/blog')
        else:
            self.write('you need to be logged in to log out first')


def blog_key(name='default'):
    return db.Key.from_path('blogs', name)


class BlogFront(BlogHandler):
    def get(self):
        posts = greetings = Post.all().order('-created')
        if not self.user:
            self.render('front.html', posts=posts)
        else:
            cur_user = self.user.name
            self.render('front.html', posts=posts, cur_user=cur_user)


class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        print post

        if not post:
            self.error(404)
            return
        if not self.user:
            self.render("permalink.html", post=post)
        else:
            cur_user = self.user.name
            self.render("permalink.html", post=post, cur_user=cur_user)


class LikeError(BlogHandler):
    def get(self):
        other_error = "You can't like your own post & can only like a post once."
        self.render("error.html", other_error=other_error)


class EditDeleteError(BlogHandler):
    def get(self):
        other_error = "You can only edit or delete posts you have created."
        self.render("error.html", other_error=other_error)


class NewPost(BlogHandler):
    def get(self):
        if self.user:
            self.render("newpost.html")
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            return self.redirect('/login')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent=blog_key(), subject=subject, content=content,
                     created_by=User.by_name(self.user.name).name, likes=0,
                     liked_by=[])

            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
            pid = p.key().id()
            print "pid = ", str(pid)
            n1 = User.by_name(self.user.name).name
            print "post created by", n1
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject, content=content,
                        error=error)


class UpdatePost(BlogHandler):
    def get(self, post_id):
        if not self.user:
            return self.redirect('/login')
        else:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            n1 = post.created_by
            n2 = self.user.name
            print "n1 = ", n1
            print "n2 = ", n2
            if n1 == n2:
                key = db.Key.from_path('Post', int(post_id), parent=blog_key())
                post = db.get(key)
                print "post = ", post
                error = ""
                self.render("updatepost.html", subject=post.subject,
                            content=post.content, error=error)
            else:
                self.redirect("/editDeleteError")

    def put(self, post_id):
        if not self.user:
            return self.redirect("/login")
        else:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            n1 = post.created_by
            n2 = self.user.name
            print "n1 = ", n1
            print "n2 = ", n2
            if n1 == n2:
                subject = self.request.get('subject')
                content = self.request.get('content')
                key = db.Key.from_path('Post', int(post_id), parent=blog_key())
                p = db.get(key)
                p.subject = self.request.get('subject')
                p.content = self.request.get('content')
                p.put()
                self.redirect('/blog/%s' % str(p.key().id()))
                pid = p.key().id()
                print "pid = ", str(pid)


class LikePost(BlogHandler):
    def get(self, post_id):
        if not self.user:
            return self.redirect('/login')
        else:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            author = post.created_by
            current_user = self.user.name

            if author == current_user or current_user in post.liked_by:
                self.redirect('/likeError')
            else:
                post.likes = post.likes + 1
                post.liked_by.append(current_user)
                post.put()
                self.redirect('/')


class DeletePost(BlogHandler):
    def post(self, post_id):
        if not self.user:
            return self.redirect('/login')
        else:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            n1 = post.created_by
            n2 = self.user.name

            if n1 == n2:
                key = db.Key.from_path('Post', int(post_id), parent=blog_key())
                post = db.get(key)
                post.delete()
                self.render("deletepost.html")
            else:
                self.redirect("/editDeleteError")

class NewComment(BlogHandler):
    def get(self, post_id):
        #
        # Display the new comment page
        #
        if not self.user:
            error = "You must be logged in to comment"
            self.redirect("/login")
            return
        post = Post.get_by_id(int(post_id), parent=blog_key())
        subject = post.subject
        content = post.content
        self.render("newcomment.html", subject=subject, 
                    content=content, pkey=post.key())
    def post(self, post_id):
        #
        # New comment was made
        #
        # make sure post_id exists
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if not post:
            self.error(404)
            return
        # make sure user is signed in
        if not self.user:
            return self.redirect('login')
        # create comment
        comment = self.request.get('comment')
        if comment:
            c = Comment(comment=comment, post=post_id, parent=self.user.key())
            c.put()
            self.redirect('/blog/%s' % str(post_id))
        else:
            error = "please provide a comment!"
            self.render("permalink.html", post = post, 
                        content=content, error=error)

class UpdateComment(BlogHandler):
    def get(self, post_id, comment_id):
        post = Post.get_by_id( int(post_id), parent=blog_key() )
        comment = Comment.get_by_id( int(comment_id), parent=self.user.key() )
        if comment:
            self.render("updatecomment.html", subject=post.subject, 
                        content=post.content, comment=comment.comment)
        else:
            self.redirect('/commenterror')
    def post(self, post_id, comment_id):
        comment = Comment.get_by_id( int(comment_id), parent=self.user.key() )
        if comment.parent().key().id() == self.user.key().id():
            comment.comment = self.request.get('comment')
            comment.put()
            self.redirect( '/blog/%s' % str(post_id) )
        else:
            other_error = "There was an error updating the comment"
            self.render("error.html", other_error=other_error)

class DeleteComment(BlogHandler):
    def get(self, post_id, comment_id):
        post = Post.get_by_id( int(post_id), parent=blog_key() )
        # this ensures the user created the comment
        comment = Comment.get_by_id( int(comment_id), parent=self.user.key() )
        if comment:
            comment.delete()
            self.redirect('/blog/%s' % str(post_id))
        else:
            self.redirect('/commenterror')

class CommentError(BlogHandler):
    def get(self):
        self.write('You can only edit or delete comments you have created.')


app = webapp2.WSGIApplication([('/', BlogFront),
            ('/blog/?', BlogFront),
            ('/blog/([0-9]+)', PostPage),
            ('/blog/newpost', NewPost),
            ('/blog/([0-9]+)/updatepost', UpdatePost),
            ('/blog/([0-9]+)/newcomment', NewComment),
            ('/blog/([0-9]+)/updatecomment/([0-9]+)', UpdateComment),
            ('/blog/([0-9]+)/deletecomment/([0-9]+)', DeleteComment),
            ('/commenterror', CommentError),
            ('/blog/([0-9]+)/like', LikePost),
            ('/signup', Register),
            ('/blog/([0-9]+)/deletepost', DeletePost),
            ('/login', Login),
            ('/logout', Logout),
            ('/editDeleteError', EditDeleteError),
            ('/likeError', LikeError)],
                              debug=True)
