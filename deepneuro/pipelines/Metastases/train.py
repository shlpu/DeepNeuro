
import os

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = '1'

from deepneuro.data.data_collection import DataCollection
from deepneuro.augmentation.augment import Flip_Rotate_2D, ExtractPatches, MaskData, Downsample, Copy
from deepneuro.models.unet import UNet
from deepneuro.models.timenet import TimeNet
from deepneuro.outputs.inference import ModelPatchesInference
from deepneuro.models.model import load_old_model
from deepneuro.postprocessing.label import BinarizeLabel, LargestComponents, FillHoles

# Temporary
from keras.utils import plot_model
import glob

def train_Segment_GBM(data_directory, val_data_directory):

    # Define input modalities to load.
    training_modality_dict = {'input_modalities': 
    ['*FLAIR*nii.gz', ['*T2SPACE*nii.gz'], ['MPRAGE_POST_r_T2.nii.gz'], ['MPRAGE_Pre_r_T2.nii.gz']],
    'ground_truth': [['MPRAGE_POST_r_T2_AUTO-label_EG.nii.gz']]}
    testing_modality_dict = {'input_modalities': 
    ['*FLAIR*nii.gz', ['*T2SPACE*nii.gz'], ['MPRAGE_POST_r_T2.nii.gz'], ['MPRAGE_Pre_r_T2.nii.gz']]}

    load_data = False
    train_model = False
    load_test_data = False
    predict = True

    training_data = '/mnt/jk489/QTIM_Databank/DeepNeuro_Datasets/METS_Prediction_training_data.h5'
    model_file = '/mnt/jk489/QTIM_Databank/DeepNeuro_Datasets/METS_Prediction.h5'
    testing_data = '/mnt/jk489/QTIM_Databank/DeepNeuro_Datasets/METS_Prediction_testing_data.h5'

    pretrained_model_file = None

    # Write the data to hdf5
    if (not os.path.exists(training_data) and train_model) or load_data:

        # Create a Data Collection
        training_data_collection = DataCollection(data_directory, modality_dict=training_modality_dict, verbose=True)
        training_data_collection.fill_data_groups()

        # Define patch sampling regions
        def brain_region(data):
            return (data['ground_truth'] != 1) & (data['input_modalities'] != 0)
        def roi_region(data):
            return data['ground_truth'] == 1
        def empty_region(data):
            return data['input_modalities'] == 0

        # Add patch augmentation
        patch_augmentation = ExtractPatches(patch_shape=(32, 32, 32), patch_region_conditions=[[empty_region, .05], [brain_region, .25], [roi_region, .7]], data_groups=['input_modalities', 'ground_truth'], patch_dimensions={'ground_truth': [1, 2, 3], 'input_modalities': [1, 2, 3]})
        training_data_collection.append_augmentation(patch_augmentation, multiplier=2000)

        # Write data to hdf5
        training_data_collection.write_data_to_file(training_data)

    if train_model:
        # Or load pre-loaded data.
        training_data_collection = DataCollection(data_storage=training_data, verbose=True)
        training_data_collection.fill_data_groups()

        # Add left-right flips
        flip_augmentation = Flip_Rotate_2D(flip=True, rotate=False, data_groups=['input_modalities', 'ground_truth'])
        training_data_collection.append_augmentation(flip_augmentation, multiplier=2)

        if pretrained_model_file is None:
            # Define model parameters and Create U-Net
            model_parameters = {'input_shape': (32, 32, 32, 4),
                            'downsize_filters_factor': 1,
                            'pool_size': (2, 2, 2), 
                            'filter_shape': (5, 5, 5), 
                            'dropout': 0, 
                            'batch_norm': True, 
                            'initial_learning_rate': 0.000001, 
                            'output_type': 'binary_label',
                            'num_outputs': 1, 
                            'activation': 'relu',
                            'padding': 'same', 
                            'implementation': 'keras',
                            'depth': 4,
                            'max_filter': 512}
            unet_model = UNet(**model_parameters)
        else:
            unet_model = load_old_model(pretrained_model_file)

        plot_model(unet_model.model, to_file='model_image_dn.png', show_shapes=True)
        training_parameters = {'input_groups': ['input_modalities', 'ground_truth'],
                        'output_model_filepath': model_file,
                        'training_batch_size': 32,
                        'num_epochs': 1000,
                        'training_steps_per_epoch': 20}
        unet_model.train(training_data_collection, **training_parameters)
    else:
        unet_model = load_old_model(model_file)

    if predict:
        testing_data_collection = DataCollection(val_data_directory, modality_dict=testing_modality_dict, verbose=True)
        testing_data_collection.fill_data_groups()

        if load_test_data:
            # Write data to hdf5
            testing_data_collection.write_data_to_file(testing_data)

        testing_parameters = {'inputs': ['input_modalities'], 
                        'output_filename': 'mets_prediction.nii.gz',
                        'batch_size': 250,
                        'patch_overlaps': 6,
                        'output_patch_shape': (26, 26, 26, 4),
                        'save_all_steps': True}

        prediction = ModelPatchesInference(**testing_parameters)

        label_binarization = BinarizeLabel(postprocessor_string='_label')

        prediction.append_postprocessor([label_binarization])

        unet_model.append_output([prediction])
        unet_model.generate_outputs(testing_data_collection)


if __name__ == '__main__':

    data_directory = ['/mnt/jk489/QTIM_Databank/QTIM_CLINICAL/Preprocessed/PEM/TRAIN', '/mnt/jk489/QTIM_Databank/QTIM_CLINICAL/Preprocessed/BRE/TRAIN']
    val_data_directory = ['/mnt/jk489/QTIM_Databank/QTIM_CLINICAL/Preprocessed/PEM/VAL', '/mnt/jk489/QTIM_Databank/QTIM_CLINICAL/Preprocessed/BRE/VAL']

    train_Segment_GBM(data_directory, val_data_directory)