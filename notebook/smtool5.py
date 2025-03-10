# -*- coding: utf-8 -*-
"""smtool5.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1-OEUNdAiFB8Fax7VDjwsTiDYEnF4wo1F
"""

!pip install datasets

pip install tensorflow datasets matplotlib

import tensorflow as tf
import numpy as np
from datasets import load_dataset

"""**Load smart contract dataset from HuggingFace**"""

big_multilabel_dataset = load_dataset(
    path="mwritescode/slither-audited-smart-contracts",
    name="big-multilabel",
    trust_remote_code=True
)

"""Clean Data"""

def clean_data(dataset):
  cleaned_data = []
  for data in dataset:
    # clean the bytecode and the 4 output that represents if the contract is safe
    if (len(data['bytecode']) > 4):
      new_slither_output = []
      for output in data['slither']:
         if (output > 4):
           new_slither_output.append(output - 1)
         elif (output < 4):
           new_slither_output.append(output)
      data['slither']=new_slither_output
      cleaned_data.append(data)
  return cleaned_data

cleaned_training_data = clean_data(big_multilabel_dataset["train"])
cleaned_validation_data = clean_data(big_multilabel_dataset["validation"])
cleaned_test_data = clean_data(big_multilabel_dataset["test"])

len(cleaned_training_data), len(cleaned_validation_data), len(cleaned_test_data)

def split_text_into_chars(text, length):
  return " ".join([text[i:i+length] for i in range(0, len(text), length)])

train_bytecode = [split_text_into_chars(data['bytecode'],2) for data in cleaned_training_data]
test_bytecode = [split_text_into_chars(data['bytecode'],2) for data in cleaned_test_data]
val_bytecode = [split_text_into_chars(data['bytecode'],2) for data in  cleaned_validation_data]

# Convert labels to binary vectors
import numpy as np

def labels_to_binary(y, num_labels):
  """
  Converts the labels into binary format depending on the total number of labels,
  for example: y = [1,4], num_labels = 5, y_binary = [0,1,0,0,1,0]
  """
  y_binary = np.zeros((len(y), num_labels), dtype=float)
  for i, label_indices in enumerate(y):
      y_binary[i, label_indices] = 1
  return y_binary

# Extract 'slither' values from cleaned datasets
training_slither = [data['slither'] for data in cleaned_training_data] # Define training_slither by extracting 'slither' from cleaned_training_data
validation_slither = [data['slither'] for data in cleaned_validation_data] # Define validation_slither by extracting 'slither' from cleaned_validation_data
test_slither = [data['slither'] for data in cleaned_test_data] # Define test_slither by extracting 'slither' from cleaned_test_data


num_classes = len(np.unique(np.concatenate(training_slither)))

train_labels_binary = labels_to_binary(training_slither, num_classes)
valid_labels_binary = labels_to_binary(validation_slither, num_classes)
test_labels_binary = labels_to_binary(test_slither, num_classes)

def transform_labels_to_dict(labels_binary):
  labels_dict = {}
  for index in range(num_classes):
    labels_dict[f'{index}'] = []

  for labels in labels_binary:
    for index, label in enumerate(labels):
      labels_dict[f'{index}'].append(label)
  return labels_dict


validation_dict = transform_labels_to_dict(valid_labels_binary)
train_dict = transform_labels_to_dict(train_labels_binary)
test_dict = transform_labels_to_dict(test_labels_binary)

train_dataset = tf.data.Dataset.from_tensor_slices((train_bytecode, train_dict)).batch(32).prefetch(tf.data.AUTOTUNE)
validation_dataset = tf.data.Dataset.from_tensor_slices((val_bytecode, validation_dict)).batch(32).prefetch(tf.data.AUTOTUNE)
test_dataset = tf.data.Dataset.from_tensor_slices((test_bytecode, test_dict)).batch(32).prefetch(tf.data.AUTOTUNE)

"""**Create the TextVectorizer layer**"""

max_tokens = 10000 # Define the maximum number of tokens
output_seq_len = 250  # Define the output sequence length

text_vectorizer = tf.keras.layers.TextVectorization(
    split="whitespace",
    max_tokens=max_tokens, # Use the defined max_tokens
    output_sequence_length=output_seq_len # Use the defined output_seq_len
)

text_vectorizer.adapt(tf.data.Dataset.from_tensor_slices(train_bytecode).batch(32).prefetch(tf.data.AUTOTUNE))

bytecode_vocab = text_vectorizer.get_vocabulary()
print(f"Number of different characters in vocab: {len(bytecode_vocab)}")
print(f"5 most common characters: {bytecode_vocab[:5]}")
print(f"5 least common characters: {bytecode_vocab[-5:]}")

"""**Create the Embedding layer**"""

embedding_layer = tf.keras.layers.Embedding(
    input_dim=len(bytecode_vocab),
    input_length=output_seq_len,
    output_dim=128,
    mask_zero=True, # Conv layers do not support masking but RNNs do
    name="embedding_layer"
)

"""**Create the model**"""

# Create input layer
from tensorflow.keras import layers # Import layers from tensorflow.keras
inputs = layers.Input(shape=(1,), dtype=tf.string)

# Create vectorization layer
x = text_vectorizer(inputs)

# Create embedding layer
x = embedding_layer(x)

# Create the LSTM layer
x = layers.GRU(units = 64, activation='tanh', return_sequences=True)(x)
x = layers.GRU(units = 32, activation='tanh')(x)
x = layers.Dropout(rate=0.2)(x)
x = layers.Dense(32, activation='relu')(x)

# Create the output layer
outputs = []
for index in range(num_classes):
  output = layers.Dense(1, activation="sigmoid", name=f'{index}')(x)
  outputs.append(output)

model_2 = tf.keras.Model(inputs = inputs, outputs = outputs, name="model_2")

"""**Compile the model**"""

losses={}
metrics={}
for index in range(num_classes):
  losses[f'{index}'] = "binary_crossentropy"
  metrics[f'{index}'] = ['accuracy']

model_2.compile(loss=losses, optimizer=tf.keras.optimizers.Adam(learning_rate=1e-03), metrics=metrics)

"""**Fit the model**"""

history_1 = model_2.fit(train_dataset,
                        epochs=20,
                        validation_data=validation_dataset,
                        callbacks=[
                                   tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss',
                                                                        patience=5),
                                   tf.keras.callbacks.ModelCheckpoint(filepath=f"model_experiments/model_2.keras",
                                                                      monitor='val_loss',
                                                                      verbose=0,
                                                                      save_best_only=True)
                                  ])

"""**Predictions**"""

model_2 = tf.keras.models.load_model(filepath="model_experiments/model_2.keras")
model_2_preds_probs = model_2.predict(test_dataset)

def convert_preds_probs_to_preds(preds_probs):
    preds = []
    for pred_prob in preds_probs:
        converted_pred_prob = [1 if value[0] >= 0.5 else 0 for value in pred_prob]
        preds.append(converted_pred_prob)
    preds_dict = {}
    for index in range(len(preds)):
        preds_dict[f'{index}'] = preds[index]
    return preds_dict

model_2_preds = convert_preds_probs_to_preds(model_2_preds_probs)

from sklearn.metrics import accuracy_score, precision_recall_fscore_support

def calculate_results(y_true, y_pred):
    """
    Calculates model accuracy, precision, recall and f1 score of a binary classification model.

    Args:
    y_true: true labels in the form of a 1D array
    y_pred: predicted labels in the form of a 1D array

    Returns:
    A dictionary of accuracy, precision, recall, f1-score.
    """
    # Calculate model accuracy
    model_accuracy = accuracy_score(y_true, y_pred) * 100
    # Calculate model precision, recall and f1 score using "weighted average"
    model_precision, model_recall, model_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted"
    )
    model_results = {
        "accuracy": model_accuracy,
        "precision": model_precision,
        "recall": model_recall,
        "f1": model_f1,
    }
    return model_results

def combine_results(y_true, y_pred, test_dict, model_2_preds, num_classes):
    results = {}
    for index in range(num_classes):
        results[f'{index}'] = calculate_results(
            y_true=test_dict[f'{index}'], y_pred=model_2_preds[f'{index}']
        )
    return results

import pandas as pd

results = combine_results(y_true=test_dict, y_pred=model_2_preds,
                          test_dict=test_dict, model_2_preds=model_2_preds,
                          num_classes=len(test_dict))

# Convert results dictionary to a DataFrame
results_df = pd.DataFrame(results)
print(results_df)

import pickle

# Save the trained model
model_2.save("vulnerability_detection_model.h5")

# Save the TextVectorizer for preprocessing
with open("text_vectorizer.pkl", "wb") as f:
    pickle.dump(text_vectorizer, f)

