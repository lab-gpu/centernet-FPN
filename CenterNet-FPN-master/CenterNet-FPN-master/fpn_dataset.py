import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np
import cv2
import math

from centernet.utils import draw_gaussian, gaussian_radius, draw_center
from centernet.config import cfg
from image import random_crop, _resize_image, _clip_detections, color_jittering_, lighting_, normalize_


class VOC_data(Dataset):

    def __init__(self, img_dict, data_dir, img_size=(512, 512), transform=None, label_transform=None,
                 num_class=20, output_size=(128, 128), gaussian_flag=True, test_flag=False):
        self.img_label = img_dict
        self.img_names = list(img_dict.keys())
        self.img_dir = data_dir
        self.img_size = img_size
        self.transform = transform
        self.label_transform = label_transform
        self.num_class = num_class
        self.output_size = output_size
        self.gaussian_flag = gaussian_flag
        self.test_flag = test_flag

        self._data_rng = np.random.RandomState(123)
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)
        self.eig_val = np.array([0.2141788, 0.01817699, 0.00341571], dtype=np.float32)
        self.eig_vec = np.array([
            [-0.58752847, -0.69563484, 0.41340352],
            [-0.5832747, 0.00994535, -0.81221408],
            [-0.56089297, 0.71832671, 0.41158938]
        ], dtype=np.float32)

    # return image and its label
    def __getitem__(self, index):
        img_name = self.img_names[index]
        detection = np.array(self.img_label[img_name])
        image = cv2.imread(cfg['2007_dir'] + r"/" + img_name + '.jpg')

        if self.test_flag is False:

            image, detection = _resize_image(image, detection, [512, 512])

            image = image.astype(np.float32) / 255.
            color_jittering_(self._data_rng, image)
            lighting_(self._data_rng, image, 0.1, self.eig_val, self.eig_vec)
            normalize_(image, self.mean, self.std)
            image = image.transpose((2, 0, 1))
            #########  data augmentation  #############
        else:
            image, detection = _resize_image(image, detection, [512, 512])
            image = image.astype(np.float32) / 255.
            normalize_(image, self.mean, self.std)
            image = image.transpose((2, 0, 1))

        # (20, 128, 128)
        center_heats_P2 = np.zeros((self.num_class, self.output_size[0], self.output_size[1]), dtype=np.float32)
        obj_size_P2 = np.zeros((4, self.output_size[0], self.output_size[1]), dtype=np.float32)
        center_pos_P2 = np.zeros((1, self.output_size[0], self.output_size[1]), dtype=np.float32)

        # (20, 64, 64)
        center_heats_P3 = np.zeros((self.num_class, self.output_size[0]//2, self.output_size[1]//2), dtype=np.float32)
        obj_size_P3 = np.zeros((4, self.output_size[0]//2, self.output_size[1]//2), dtype=np.float32)
        center_pos_P3 = np.zeros((1, self.output_size[0]//2, self.output_size[1]//2), dtype=np.float32)

        # (20, 32, 32)
        center_heats_P4 = np.zeros((self.num_class, self.output_size[0]//4, self.output_size[1]//4), dtype=np.float32)
        obj_size_P4 = np.zeros((4, self.output_size[0]//4, self.output_size[1]//4), dtype=np.float32)
        center_pos_P4 = np.zeros((1, self.output_size[0]//4, self.output_size[1]//4), dtype=np.float32)

        h_ratio_P2 = self.output_size[0] / self.img_size[0]
        w_ratio_P2 = self.output_size[1] / self.img_size[1]

        h_ratio_P3 = h_ratio_P2 / 2
        w_ratio_P3 = w_ratio_P2 / 2

        h_ratio_P4 = h_ratio_P2 / 4
        w_ratio_P4 = w_ratio_P2 / 4

        for i, object in enumerate(detection):
            category = int(object[-1])

            center_x = (object[0] + object[2]) / 2
            center_y = (object[1] + object[3]) / 2
            obj_w = object[2] - object[0]
            obj_h = object[3] - object[1]

            scale = math.sqrt(obj_w*obj_h)

            if scale < 64:
                map_center_x = center_x * w_ratio_P2
                map_center_y = center_y * h_ratio_P2
                obj_w = obj_w * w_ratio_P2
                obj_h = obj_h * h_ratio_P2
                # 向下取整
                center_x = int(map_center_x)
                center_y = int(map_center_y)

                obj_size_P2[:, center_y, center_x] = [obj_w, obj_h,
                                                      map_center_x - center_x,
                                                      map_center_y - center_y]
                center_pos_P2[:, center_y, center_x] = 1

                radius = gaussian_radius((math.ceil(obj_h), math.ceil(obj_w)), 0.3)
                radius = max(0, int(radius))
                draw_gaussian(center_heats_P2[category], [center_x, center_y], radius)

            elif scale >= 64 and scale < 128:
                map_center_x = center_x * w_ratio_P3
                map_center_y = center_y * h_ratio_P3
                obj_w = obj_w * w_ratio_P3
                obj_h = obj_h * h_ratio_P3
                # 向下取整
                center_x = int(map_center_x)
                center_y = int(map_center_y)

                obj_size_P3[:, center_y, center_x] = [obj_w, obj_h,
                                                      map_center_x - center_x,
                                                      map_center_y - center_y]
                center_pos_P3[:, center_y, center_x] = 1

                radius = gaussian_radius((math.ceil(obj_h), math.ceil(obj_w)), 0.3)
                radius = max(0, int(radius))
                draw_gaussian(center_heats_P3[category], [center_x, center_y], radius)

            else:
                map_center_x = center_x * w_ratio_P4
                map_center_y = center_y * h_ratio_P4
                obj_w = obj_w * w_ratio_P4
                obj_h = obj_h * h_ratio_P4
                # 向下取整
                center_x = int(map_center_x)
                center_y = int(map_center_y)

                obj_size_P4[:, center_y, center_x] = [obj_w, obj_h,
                                                      map_center_x - center_x,
                                                      map_center_y - center_y]
                center_pos_P4[:, center_y, center_x] = 1

                radius = gaussian_radius((math.ceil(obj_h), math.ceil(obj_w)), 0.3)
                radius = max(0, int(radius))
                draw_gaussian(center_heats_P4[category], [center_x, center_y], radius)

        if self.transform is not None:
            image = self.transform(image)
        else:
            image = torch.from_numpy(image)

        if self.label_transform is not None:
            center_heats_P2 = self.label_transform(center_heats_P2)
            obj_size_P2     = self.label_transform(obj_size_P2)
            center_pos_P2   = self.label_transform(center_pos_P2)
        else:
            center_heats_P2 = torch.from_numpy(center_heats_P2)
            obj_size_P2 = torch.from_numpy(obj_size_P2)
            center_pos_P2 = torch.from_numpy(center_pos_P2)

            center_heats_P3 = torch.from_numpy(center_heats_P3)
            obj_size_P3 = torch.from_numpy(obj_size_P3)
            center_pos_P3 = torch.from_numpy(center_pos_P3)

            center_heats_P4 = torch.from_numpy(center_heats_P4)
            obj_size_P4 = torch.from_numpy(obj_size_P4)
            center_pos_P4 = torch.from_numpy(center_pos_P4)

        return image, [center_heats_P2, obj_size_P2, center_pos_P2,
                       center_heats_P3, obj_size_P3, center_pos_P3,
                       center_heats_P4, obj_size_P4, center_pos_P4]

    def __len__(self):
        return len(self.img_names)
