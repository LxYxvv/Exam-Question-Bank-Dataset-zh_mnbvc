import joblib
import re
import jieba
import argparse
import os   
import glob
import requests
from tqdm import tqdm
import shutil
from docx import Document
from pathlib import Path
import textract

def remove_image_string(input_string):
    """
    从输入字符串中移除图片字符串。
    
    参数:
    input_string (str): 原始字符串。
    
    返回:
    result (str): 移除图片字符串后的结果。
    """
    pattern = r"!\[(.*?)\]\(.*?\)\{width=\".*?\" height=\".*?\"\}|!\[.*?\]\(.*?\)|\[.*?\]\{.*?\}"
    result = re.sub(pattern, "", input_string)
    return result


def remove_noise_character(input_string):
    """
    从输入字符串中移除噪声字符。
    
    参数:
    input_string (str): 原始字符串。
    
    返回:
    result (str): 移除噪声字符后的结果。
    """
    pattern = r"[>*|image|data|media|png]"
    return re.sub(pattern, "", input_string)


def one_text_pre_process(text):
    """
    对单个文本进行预处理。
    
    参数:
    text (str): 需要预处理的文本。
    
    返回:
    precessed_text_split_lines (str): 预处理后的文本。
    """
    precessed_text_split_lines = []
    
    for line in text.splitlines():
        remove_image_line = remove_image_string(line)

        if remove_image_line.strip() in ["", ">"]:
            continue

        remove_image_line = remove_noise_character(remove_image_line)
        precessed_text_split_lines.append(remove_image_line)
        
    return "\n".join(precessed_text_split_lines)


def pre_process(text_list):
    """
    对文本列表进行预处理。
    
    参数:
    text_list (list): 需要预处理的文本列表。
    
    返回:
    precessed_text_list (list): 预处理后的文本列表。
    """
    precessed_text_list = [one_text_pre_process(text) for text in text_list]
    return precessed_text_list


def dataset_map_pre_process(row):
    """
    对数据集的一行进行预处理。
    
    参数:
    row (dict): 需要预处理的数据行，字典形式。
    
    返回:
    row (dict): 预处理后的数据行，字典形式。
    """
    row["text"] = one_text_pre_process(row["text"])
    return row


def chinese_tokenizer(text):
    """
    对中文文本进行分词。
    
    参数:
    text (str): 需要分词的文本。
    
    返回:
    tokens (list): 分词后的词语列表。
    """
    tokens = jieba.cut(text)
    return list(tokens)


def get_predict_with_threshold(model, X, threshold=0.5):
    """
    对模型进行带阈值的预测。
    
    参数:
    model (object): 需要预测的模型。
    X (array-like): 需要预测的数据。
    threshold (float): 预测阈值，默认为0.9。
    
    返回:
    predictions (array-like): 预测结果。
    positive_probabilities: 预测的值
    """
    probabilities = model.predict_proba(X)
    positive_probabilities = probabilities[:, 1]
    predictions = (positive_probabilities > threshold).astype(int)
    return predictions, positive_probabilities


def change_last_folder_name(path, new_folder_name):
    """
    修改路径中的最后一个文件夹名。
    
    参数:
    path (str): 原始路径。
    new_folder_name (str): 新的文件夹名。
    
    返回:
    new_path (str): 修改后的路径。
    """
    folders = path.split('/')
    last_folder = folders[-1]
    new_path = path.replace(last_folder, new_folder_name)
    return new_path


def get_file_content(file_local):
    """
    获取文件内容。
    
    参数:
    file_local (str): 文件的本地路径。
    
    返回:
    content (str): 文件内容。
    """
    with open(file_local, "r") as f:
        return f.read()


def download_model(*, model_name, download_url):
    """
    从指定的URL下载模型并使用给定的模型名称保存。

    参数：
        model_name (str): 要下载的模型的名称。
        download_url (str): 要下载模型的URL。
    """

    # 检查模型是否已存在
    if os.path.exists(model_name):
        return

    temp_model_name = model_name + ".tmp"

    # 检查是否存在临时模型文件
    if os.path.exists(temp_model_name):
        initial_position = os.path.getsize(temp_model_name)
    else:
        initial_position = 0

    try:
        # 设置请求头部信息，用于断点续传
        headers = {'Range': f'bytes={initial_position}-'}
        response = requests.get(download_url, headers=headers, stream=True)

        # 检查响应的状态码
        response.raise_for_status()

        # 从响应头部信息获取总文件大小
        total_size = int(response.headers.get('content-range').split('/')[1])

        # 创建进度条并设置初始值为已下载的文件大小
        progress_bar = tqdm(total=total_size, unit='iB', unit_scale=True, initial=initial_position)

        with open(temp_model_name, 'ab') as f:
            for data in response.iter_content(chunk_size=1024):
                progress_bar.update(len(data))
                f.write(data)

        progress_bar.close()

        # 检查下载是否完成
        if total_size != 0 and progress_bar.n != total_size:
            print("错误：下载过程中出现问题。")

        # 将临时模型文件重命名为指定的模型名称
        os.rename(temp_model_name, model_name)
    except:
        # 如果出现异常，抛出异常并中断下载过程
        raise


def extract_text_from_docx(file_path):
    """
    解析一个docx中的文字，没有图片标签等噪点
    """
    doc = Document(file_path)
    text = ''
    for paragraph in doc.paragraphs:
        text += paragraph.text + ' '
    return text


def extract_text_from_doc(file_path):
    """
    解析一个doc中的文字，没有图片标签等噪点
    """
    text = textract.process(file_path)
    return text.decode("utf-8")


def extract_text(file_local, ext):
    return extract_text_from_docx(file_local) if ext in "docx" else extract_text_from_doc(file_local)


def detect_language(text):
    """
    解析一段文字是否为中文
    """
    chinese_count = 0
    english_count = 0
    
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            chinese_count += 1
        elif 'a' <= char.lower() <= 'z':
            english_count += 1
            
    if chinese_count > english_count:
        return 'Chinese'
    elif english_count > chinese_count:
        return 'English'
    else:
        return 'Unknown'
    

EXAMINATION_KEY_WORDS = ['考试', '试卷', '卷', '试题', '试']


def judge_examination_paper_by_file_name(file_name):
    return any(key_word in file_name for key_word in EXAMINATION_KEY_WORDS)


def write_classification_by_file_name_log(file_name):
    with open("file_name_classification.log", "a") as f:
        f.write(f"{file_name}\n")


FILE_SUFFIX = {".doc", ".docx"}


def move_files(input_dir, output_dir, threshold, model, just_by_file_name=False):
    if os.path.exists(input_dir) == False:
        raise ValueError('输入目录不存在')
    if os.path.abspath(input_dir) == os.path.abspath(output_dir):
        raise ValueError('输入目录和输出目录不能相同')
    
    os.makedirs(output_dir, exist_ok=True)
    
    all_file = []
    # 先把文件列表放到一个变量中，这样可以使用tqdm来查看进度
    for root, _, files in os.walk(input_dir):
        for file in files:
            all_file.append({
                "root": root,
                "file": file
            })
            
            
    for row in tqdm(all_file):
        root = row["root"]
        file = row["file"]

        # 文件后缀，用于解析word文档
        _, ext = os.path.splitext(file)

        if ext not in FILE_SUFFIX:
            continue

        file_local = os.path.join(root, file)

        # widnwos下的目录和ubuntu不一样
        if "\\" in file_local:
            file_local = file_local.replace("\\","/")

        target_dir = os.path.join(output_dir, os.path.relpath(root, input_dir))
        target_file = os.path.join(target_dir, file_local.split("/")[-1])

        if os.path.exists(target_file):
            continue

        try:
            # 因为库和文件编码的原因，有很小的几率存在解析失败
            text = extract_text(file_local, ext=ext)

            # 只检查中文
            if detect_language(text) != "Chinese":
                continue
        except: 
            continue
        
        # 如果从word文档中提取的字符数量过少，则使用文件名判断
        if just_by_file_name or len(text) < 50:

            predict = judge_examination_paper_by_file_name(file)

            if predict:
                write_classification_by_file_name_log(target_file)
        else:
            predictions, positive_probabilities = get_predict_with_threshold(model, [one_text_pre_process(text)], threshold)
            predict = predictions[0]
            
        # 0/1 => False/True
        if predict:
            Path(target_dir).mkdir(parents=True, exist_ok=True)
            shutil.copy(file_local, target_file)

        with open("./move_log.log","a") as f:
            f.write(f"{predict} {positive_probabilities[0]} {file_local}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_dir', type=str, required=True, help="输入目录")
    parser.add_argument('--output_dir', type=str, required=True, help="输出目录")
    parser.add_argument('--model_url', default="https://huggingface.co/datasets/ranWang/test_paper_textClassifier/resolve/main/TextClassifie-full-final.pkl", type=str, help='模型下载链接')
    parser.add_argument('--threshold', default=0.5, type=float, help='预测阈值')
    parser.add_argument("--just_by_file_name", default=0, type=int, help='是否仅仅通过文件名(0/1)')

    args = parser.parse_args()

    just_by_file_name = args.just_by_file_name

    if just_by_file_name:
        model = None
    else:
        model_file_name = "TextClassifier.pkl"
        download_model(model_name=model_file_name, download_url=args.model_url)
        model = joblib.load(model_file_name)
        
    move_files(args.input_dir, args.output_dir, args.threshold, model, args.just_by_file_name)

