from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.template import Context, RequestContext
from django.contrib.auth.models import User

from project.settings import LOGIN_REDIRECT_URL
from account.models import RegistrationForm

def login_user(request):
    state = "Please log in"
    username = ''
    password = ''

    if request.POST:
        username = request.POST.get('username')
        password = request.POST.get('password')
        if request.POST.get('next'):
            next = request.POST.get('next')
        else:
            next = LOGIN_REDIRECT_URL

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect(next)
            else:
                state = "Your Account is not active."
        else:
            state = "Invalid username/password."
    else:
        if request.GET.get('next'):
            next = request.GET.get('next')
        else:
            next = LOGIN_REDIRECT_URL

    c = Context({
        "state": state,
        "username": username,
        "next": next
        })
    return render(request, "account/login.html", c)

def logout_user(request):
    logout(request)
    if request.GET.get('next'):
        next = request.GET.get('next')
    else:
        next = LOGIN_REDIRECT_URL
    return redirect(next)


def index(request):
    pass

def register_user(request):
    a = {}
    for x in ("username", "email", "password1", "password2"):
        if request.POST.get(x):
            a[x] = request.POST[x]
    state = "Please register"

    if request.POST:
        form = RegistrationForm(request.POST, initial=a)
        if form.is_valid():
            username = a["username"]
            password = a["password1"]
            User.objects.create_user(username, a["email"], password)
            user = authenticate(username=username, password=password)
            login(request, user)
            return redirect("/chem/")
        else:
            state =" Failure."
    else:
        form = RegistrationForm()

    c =  Context({
        "state": state,
        "form": form,
        })
    return render(request, "account/register.html", c)