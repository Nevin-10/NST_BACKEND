from flask import Flask, jsonify, request, render_template, redirect, url_for, session,send_file
import pyrebase
import tensorflow as tf
import numpy as np
import PIL.Image
import os
from flask import Flask
from flask_cors import CORS
from flask import request
from flask_session import Session
#from firebase_admin import auth


app = Flask(__name__)
Session(app)
CORS(app)

app.secret_key = os.urandom(24).hex()  # Set a secret key for session management



# Enable CORS for all routes


# Configure Firebase
firebaseConfig = {
    'apiKey': "AIzaSyAhCKUMbP8GGtwkAaAEV38dKWzn6BcxS5Y",
    'authDomain': "neural-st.firebaseapp.com",
    'projectId': "neural-st",
    'measurementId': "G-7YF88TGD3Y",
    'storageBucket': "neural-st.appspot.com",
    'messagingSenderId': "690387462569",
    'appId': "1:690387462569:web:8b5709267710c33a227cb8",
    'databaseURL': "https://neural-st-default-rtdb.firebaseio.com/" }

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db=firebase.database()
storage = firebase.storage()

global user
# Load pre-trained model
def load_model():
    content_layers = ['block5_conv2']
    style_layers = ['block1_conv1', 'block2_conv1', 'block3_conv1', 'block4_conv1', 'block5_conv1']
    vgg = tf.keras.applications.VGG19(include_top=False, weights='vgg19_weights_tf_dim_ordering_tf_kernels_notop.h5')
    vgg.trainable = False

    style_extractor = vgg_layers(style_layers)
    extractor = StyleContentModel(style_layers, content_layers)

    return extractor

def vgg_layers(layer_names):
    vgg = tf.keras.applications.VGG19(include_top=False, weights='vgg19_weights_tf_dim_ordering_tf_kernels_notop.h5')
    vgg.trainable = False
    outputs = [vgg.get_layer(name).output for name in layer_names]
    model = tf.keras.Model([vgg.input], outputs)
    return model

class StyleContentModel(tf.keras.models.Model):
    def __init__(self, style_layers, content_layers):
        super(StyleContentModel, self).__init__()
        self.vgg = vgg_layers(style_layers + content_layers)
        self.style_layers = style_layers
        self.content_layers = content_layers
        self.num_style_layers = len(style_layers)
        self.vgg.trainable = False

    def call(self, inputs):
        inputs = inputs * 255.0
        preprocessed_input = tf.keras.applications.vgg19.preprocess_input(inputs)
        outputs = self.vgg(preprocessed_input)
        style_outputs, content_outputs = (outputs[:self.num_style_layers], outputs[self.num_style_layers:])
        style_outputs = [gram_matrix(style_output) for style_output in style_outputs]
        content_dict = {content_name: value for content_name, value in zip(self.content_layers, content_outputs)}
        style_dict = {style_name: value for style_name, value in zip(self.style_layers, style_outputs)}
        return {'content': content_dict, 'style': style_dict}

def gram_matrix(input_tensor):
    result = tf.linalg.einsum('bijc,bijd->bcd', input_tensor, input_tensor)
    input_shape = tf.shape(input_tensor)
    num_locations = tf.cast(input_shape[1] * input_shape[2], tf.float32)
    return result / (num_locations)

def load_img(path_to_img):
    max_dim = 512
    img = tf.io.read_file(path_to_img)
    img = tf.image.decode_image(img, channels=3)
    img = tf.image.convert_image_dtype(img, tf.float32)

    shape = tf.cast(tf.shape(img)[:-1], tf.float32)
    long_dim = max(shape)
    scale = max_dim / long_dim

    new_shape = tf.cast(shape * scale, tf.int32)

    img = tf.image.resize(img, new_shape)
    img = img[tf.newaxis, :]
    return img

def style_transfer(content_image_path, style_image_path, output_path, epochs, steps_per_epoch):
    content_image = load_img(content_image_path)
    style_image = load_img(style_image_path)

    extractor = load_model()
    style_targets = extractor(style_image)['style']
    content_targets = extractor(content_image)['content']

    image = tf.Variable(content_image)

    opt = tf.keras.optimizers.Adam(learning_rate=0.02, beta_1=0.99, epsilon=1e-1)
    style_weight = 1e-2
    content_weight = 1e4

    @tf.function()
    def train_step(image):
        with tf.GradientTape() as tape:
            outputs = extractor(image)
            loss = style_content_loss(outputs)

        grad = tape.gradient(loss, image)
        opt.apply_gradients([(grad, image)])
        image.assign(clip_0_1(image))

   


    def style_content_loss(outputs):
        style_outputs = outputs['style']
        content_outputs = outputs['content']
        style_loss = tf.add_n([tf.reduce_mean((style_outputs[name] - style_targets[name]) ** 2) for name in style_outputs.keys()])
        style_loss *= style_weight / len(style_outputs)

        content_loss = tf.add_n([tf.reduce_mean((content_outputs[name] - content_targets[name]) ** 2) for name in content_outputs.keys()])
        content_loss *= content_weight / len(content_outputs)

        loss = style_loss + content_loss
        return loss

    def clip_0_1(image):
        return tf.clip_by_value(image, clip_value_min=0.0, clip_value_max=1.0)

    for _ in range(epochs):
        for _ in range(steps_per_epoch):
            train_step(image)

    generated_image_array = np.array(image[0].numpy() * 255, dtype=np.uint8)
    generated_image_pil = PIL.Image.fromarray(generated_image_array)
    generated_image_pil.save(output_path)



@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        email = request.json.get('email')
        password = request.json.get('password')
        try:
            
            user = auth.sign_in_with_email_and_password(email, password)
            session['user'] = user
            print(user)
            print("&&&&&")
            print(session["user"]["localId"])
            
            return jsonify({'success': True, 'message': 'Login successful'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 200  
    return jsonify({'success': False, 'error': 'Method not allowed'}), 405  # Method Not Allowed status code


@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.json.get('email')

    if not email:
        return jsonify({'error': 'Email address is required'}), 400

    try:
        reset_email = auth.send_password_reset_email(email)
        return jsonify({'message': 'Password reset email sent successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    


@app.route('/user_info',methods=['GET'])
def user_info():
    if 'user' not in session:
        return jsonify({'error': 'User not logged in'}), 401  # Unauthorized

    token = session['user']
    try:
        user_info = auth.get_account_info(token)
        return jsonify({'user': user_info}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500  # Internal Server Error

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    if data:
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        if name and email and password:
            try:
                user = auth.create_user_with_email_and_password(email, password,)
                # Save user data to Firebase Realtime Database
                user_data = {
                    'name': name,
                    'email': email
                    # You can add more user data fields here if needed
                }
                db.child('users').child(user['localId']).set(user_data)
                auth.send_email_verification(user['idToken'])
                return jsonify({'success': True, 'message': 'User created successfully'}), 200
            except:
                return jsonify({'success': False, 'error': 'Email already exists'}), 400
        else:
            return jsonify({'success': False, 'error': 'Invalid data'}), 400
    else:
        return jsonify({'success': False, 'error': 'No data provided'}), 400


    
# Style Transfer endpoint
@app.route('/transfer_style', methods=['GET', 'POST'])
def transfer_style():
    if 'user' not in session:
        return redirect(url_for('login'))
      


    if request.method == 'POST':
        print("jofdojfdjjdovjdovjodjvdjnvjjjjjjjjjjjjjj")
         
        user_id = session["user"]["localId"]
        print(user_id)
        content_file = request.files['content']
        style_file = request.files['style']
        epochs = int(request.form.get('epochs', 1))
        steps_per_epoch = int(request.form.get('steps_per_epoch', 5))

        content_filename = 'contentpic.jpg'
        style_filename = 'stylepic.jpg'
        output_filename = 'generated_image.jpg'

        content_path = os.path.join('content', content_filename)
        style_path = os.path.join('style', style_filename)
        output_path = os.path.join('generated', output_filename)

        content_file.save(content_path)
        style_file.save(style_path)

        style_transfer(content_path, style_path, output_path, epochs, steps_per_epoch)

       # Store URLs in Firebase Realtime Database
        content_upload = storage.child('content').child(f'content_{user_id}').put(content_path)
        content_url = storage.child('content').child(f'content_{user_id}').get_url(content_upload['downloadTokens'])

        style_upload = storage.child('style').child(f'style_{user_id}').put(style_path)
        style_url = storage.child('style').child(f'style_{user_id}').get_url(style_upload['downloadTokens'])

        generated_upload = storage.child('generated').child(f'generated_{user_id}').put(output_path)
        generated_url = storage.child('generated').child(f'generated_{user_id}').get_url(generated_upload['downloadTokens'])

        # Store URLs in the database
        db.child('users').child(user_id).child("Images").push({
            "content": content_url,
            "style": style_url,
            "generated": generated_url
        })
        return jsonify({'result': 'success', 'generated_image': output_filename})


@app.route('/generated_image/<path:image_name>')
def get_generated_image(image_name):
    generated_image_path = os.path.join('generated', image_name)
    if os.path.exists(generated_image_path):
        return send_file(generated_image_path, mimetype='image/jpeg')
    else:
        return jsonify({'message': 'Image not yet generated. Please wait for the process to complete.'})
if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True)
'''# Style Transfer endpoint
@app.route('/transfer_style', methods=['POST'])
def transfer_style():
    if 'user' not in session:
        return jsonify({'error': 'User not logged in'})

    #user_id = session['user']['localId']
    print(user)
    # Upload content image
    content_file = request.files['content']
    content_filename = f'content.jpg'
    content_path = os.path.join('content', content_filename)
    content_file.save(content_path)

    # Upload style image
    style_file = request.files['style']
    style_filename = f'style.jpg'
    style_path = os.path.join('style', style_filename)
    style_file.save(style_path)

    # Retrieve additional parameters
    epochs = int(request.form.get('epochs', 1))
    steps_per_epoch = int(request.form.get('steps_per_epoch', 5))

    # Perform style transfer
    output_filename = f'generated_image.jpg'
    output_path = os.path.join('generated', output_filename)
    style_transfer(content_path, style_path, output_path, epochs, steps_per_epoch)

    # Store URLs in Firebase Realtime Database
    content_upload = storage.child('users').put(content_path)
    content_url = storage.child('users').get_url(content_upload['downloadTokens'])

    style_upload = storage.child('users').put(style_path)
    style_url = storage.child('users').get_url(style_upload['downloadTokens'])

    generated_upload = storage.child('users').put(output_path)
    generated_url = storage.child('users').get_url(generated_upload['downloadTokens'])

    # Store URLs in the database
    db.child('users').child("Images").push({
        "content": content_url,
        "style": style_url,
        "generated": generated_url
    })

    return jsonify({'result': 'success', 'generated_image': output_filename})
'''

