"""
This module takes care of starting the API Server, Loading the DB and Adding the endpoints
"""
import os
from flask import Flask, request, jsonify, url_for
from flask_migrate import Migrate
from flask_swagger import swagger
from flask_cors import CORS
from utils import APIException, generate_sitemap
from admin import setup_admin
from models import db, User, People, FavoritePeople, TokenBlockedlist
#from models import Person

from flask_jwt_extended import create_access_token
from flask_jwt_extended import get_jwt_identity, get_jwt
from flask_jwt_extended import jwt_required
from flask_jwt_extended import JWTManager
 
from datetime import date, time, datetime, timezone, timedelta

from flask_bcrypt import Bcrypt #libreria para incriptaciones

app = Flask(__name__)
app.url_map.strict_slashes = False

#Inicio mi instancia de JWL
app.config["JWT_SECRET_KEY"] = os.getenv("FLASK_APP_KEY")  # Change this!
jwt = JWTManager(app)

bcrypt = Bcrypt(app) #inicio mi instancia de Bcrypt

db_url = os.getenv("DATABASE_URL")
if db_url is not None:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:////tmp/test.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

MIGRATE = Migrate(app, db)
db.init_app(app)
CORS(app)
setup_admin(app)

# Handle/serialize errors like a JSON object
@app.errorhandler(APIException)
def handle_invalid_usage(error):
    return jsonify(error.to_dict()), error.status_code

# generate sitemap with all your endpo s
@app.route('/')
def sitemap():
    return generate_sitemap(app)

@app.route('/user', methods=['GET'])
def handle_hello():
    users = User.query.all()
    users = list(map(lambda item: item.serialize(), users)) 
    print(users)
    return jsonify(users), 200

@app.route('/register', methods=['POST'])
def register_user():
    #recibir el body en json, des.jsonificarlos y almacenarlo en la variable body
    body =  request.get_json()

    email = body["email"]
    name = body["name"]
    password = body["password"]
    is_active = body["is_active"]

    #validaciones 
    if body is None:
        raise APIException("You need to specify the request body as json object", status_code=400)
    if "email" not in body:
        raise APIException("You need to specify the email", status_code=400)

    password_encrypted = bcrypt.generate_password_hash(password,10).decode('utf-8')
    
    #creada la clase user en la variable new_user
    new_user = User(email=email, name=name, password=password, is_active=is_active)

    db.session.add(new_user) #agregamos el nuevo usuario a la base de datos
    db.session.commit() #luego guardamos los cambios en la base de datos
    
    return jsonify({"mensaje":"usuario creado correctamente"}) , 201 

@app.route('/user/<int:id>', methods=['GET'])
def get_specific_user(id):
    user = User.query.get(id)

    return jsonify(user.serialize()), 200

@app.route('/get-user', methods=['POST'])
def get_specific_user2():
    body = request.get_json()
    id = body["id"]
    user = User.query.get(id)
    return jsonify(user.serialize()), 200
   
@app.route('/get-user', methods=['DELETE'])
def delete_specific_user():
    body = request.get_json()
    id = body["id"]

    user = User.query.get(id)

    db.session.delete(user)
    db.session.commit()
    return jsonify("usuario borrado"), 200

@app.route('/get-user', methods=['PUT'])
def edit_user():
    body = request.get_json()
    id = body["id"]
    name = body["name"]

    user = User.query.get(id)
    user.name = name #Modificar nombre de usuario

    db.session.commit()

    return jsonify(user.serialize()), 200

@app.route('/add-favorite/people', methods=['POST'])
def add_favorite_people():
    body = request.get_json()
    user_id = body["user_id"]
    people_id = body["people_id"]

    character = People.query.get(people_id)
    if not character:
        raise APIException('Personaje no encontrado', status_code=404)

    user = User.query.get(user_id)
    if not user:
        raise APIException('Usuario no encontrado', status_code=404)

    fav_exist = FavoritePeople.query.filter_by(user_id=user.id, people_id = character.id).first() is not None

    if fav_exist:
        raise APIException('Usuario ya lo tiene agregado a Favoritos', status_code=404)

    favorite_people = FavoritePeople(user_id=user.id, people_id=character.id)
    db.session.add(favorite_people)
    db.session.commit()

    return jsonify(favorite_people.serialize()), 201

@app.route('/favorites', methods=['POST'])
def list_favorites():
    body = request.get_json()
    user_id = body["user_id"]
    if not user_id:
        raise APIException('Faltan datos', status_code=404)

    user = User.query.get(user_id)
    if not user:
        raise APIException('Usuario no encontrado', status_code=404)

    user_favorites = FavoritePeople.query.filter_by(user_id=user.id).all() 
    user_favorites_final = list(map(lambda item: item.serialize(), user_favorites))

    #user_planets = FavoritePeople.query.filter_by(user_id=user.id).all() 
    #user_planets_final = list(map(lambda item: item.serialize(), user_favorites))

    
    #user_favorites_all = user_favorites_final + user_planets_final

    return jsonify(user_favorites_final), 200

@app.route('/login', methods=['POST'])
def login():
    email=request.get_json()["email"]
    password = request.get_json()["password"]

    user = User.query.filter_by(email=email).first()

    if user is None:
        return jsonify({"message":"Login failed"}), 401

    #validar el password encriptado
    if not bcrypt.check_password_hash(user.password, password):
        return jsonify({"message":"Login failed"}), 401
    
    access_token = create_access_token(identity=user.id)
    return jsonify({"token":access_token}), 200


@app.route("/protected", methods=["GET"])
@jwt_required()
def protected():
    # Access the identity of the current user with get_jwt_identity
    current_user = get_jwt_identity()
    user = User.query.get(current_user)

    token = verificacionToken(get_jwt()["jti"]) #reuso la función de verificacion de token
    print(token)
    if token:
       raise APIException('Token está en lista negra', status_code=404)

    print("EL usuario es: ", user.name)
    return jsonify({"message":"Estás en una ruta protegida", "name": user.name}), 200

@app.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"] #identificador de jwt
    now = datetime.now(timezone.utc)

    #identificamos al usuario
    current_user = get_jwt_identity()
    user = User.query.get(current_user)

    tokenblocked = TokenBlockedlist(token=jti, created_at=now, email=user.email)
    db.session.add(tokenblocked)
    db.session.commit()

    return jsonify({"message":"logout successfully"})

# this only runs if `$ python src/app.py` is executed
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=PORT, debug=False)
