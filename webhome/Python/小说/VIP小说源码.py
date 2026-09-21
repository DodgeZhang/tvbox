
import requests
import re

with open('斗破苍穹之纳兰无敌.txt', 'a') as f:
    for x in range(0, 50):
        rsp = requests.get('http://www.doupoxs.com/nalanwudi/{}.html'.format(2752 + x))
        rsp.encoding = rsp.apparent_encoding

        result = re.findall('<p>(.*?)</p>', rsp.text)
        result = result[1:len(result) - 1]
        f.writelines(result)

import jieba.analyse
from wordcloud import WordCloud
from imageio import imread

with open('斗破苍穹之纳兰无敌.txt', 'r') as f:

    text = f.read()

    tags = jieba.analyse.extract_tags(text, topK=50, withWeight=True)

    with open('word.txt', 'a') as f1:
        for tag in tags:
            f1.write('{0}\t{1}\n'.format(tag[0], int(tag[1] * 1000)))

    font = r'C:\\Windows\\Fonts\\simfang.ttf'

    wc = WordCloud(font_path=font, background_color='White', max_words=50, width=600, height=800)
    with open('word.txt', 'r') as f2:
        wc.generate(f2.read())
        wc.to_file('2.png')

